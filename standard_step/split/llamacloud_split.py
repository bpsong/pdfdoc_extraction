"""Split bundled PDFs into child documents using LlamaCloud decisions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.db.connection import connect, json_loads
from modules.db.repositories import AuditRepository, BatchRepository, DocumentRepository
from modules.exceptions import TaskError
from modules.utils import generate_unique_filepath, sanitize_filename
from standard_step.split.llamacloud_split_adapter import (
    LlamaCloudSplitAdapter,
    SplitResult,
    SplitSegment,
)


def create_split_pdf(source_pdf_path: str, output_pdf_path: str, pages_1_indexed: list[int]) -> None:
    """Create one child PDF from 1-indexed source pages.

    Args:
        source_pdf_path: Source PDF path.
        output_pdf_path: Destination PDF path.
        pages_1_indexed: Exact 1-indexed source pages to copy.

    Raises:
        TaskError: If pages are invalid or PDF writing fails.
    """
    if not pages_1_indexed:
        raise TaskError("Cannot create a split PDF without pages.")

    source_path = Path(source_pdf_path)
    output_path = Path(output_pdf_path)
    reader = PdfReader(str(source_path))
    page_count = len(reader.pages)

    invalid_pages = [page for page in pages_1_indexed if page < 1 or page > page_count]
    if invalid_pages:
        raise TaskError(
            f"Split pages {invalid_pages} are outside source PDF page range 1-{page_count}."
        )

    writer = PdfWriter()
    for page_number in pages_1_indexed:
        writer.add_page(reader.pages[page_number - 1])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output_file:
        writer.write(output_file)


class LlamaCloudSplitTask(BaseTask):
    """Pipeline task that fans out a source PDF into child documents."""

    def __init__(self, config_manager: ConfigManager, **params: Any) -> None:
        """Initialize the split task."""
        super().__init__(config_manager=config_manager, **params)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.enabled = bool(params.get("enabled", False))
        self.categories = list(params.get("categories") or [])
        self.api_key = str(params.get("api_key") or "")
        self.configuration_id = params.get("configuration_id")
        self.project_id = params.get("project_id")
        self.organization_id = params.get("organization_id")
        self.allow_uncategorized = str(params.get("allow_uncategorized", "include"))
        self.poll_interval_seconds = float(params.get("poll_interval_seconds", 1.0))
        self.timeout_seconds = float(params.get("timeout_seconds", 7200.0))
        self.adapter = params.get("adapter")

        split_dir = params.get("split_dir")
        self.split_dir: Path | None = Path(str(split_dir)) if isinstance(split_dir, str) and split_dir.strip() else None

    def on_start(self, context: dict[str, Any]) -> None:
        """Initialize context and log task start."""
        self.initialize_context(context)
        self.logger.info("Starting LlamaCloudSplitTask for %s", context.get("file_path"))

    def validate_required_fields(self, context: dict[str, Any]) -> None:
        """Validate split task configuration and current context."""
        if self.split_dir is None:
            raise TaskError("LlamaCloudSplitTask requires split_dir.")
        if not self.enabled:
            return
        if self.allow_uncategorized not in {"include", "forbid", "omit"}:
            raise TaskError("allow_uncategorized must be one of: include, forbid, omit.")
        if not context.get("batch_id") or not context.get("document_id"):
            raise TaskError("LlamaCloudSplitTask requires batch_id and document_id in context.")
        file_path = context.get("file_path")
        if not file_path:
            raise TaskError("LlamaCloudSplitTask requires file_path in context.")
        if not Path(str(file_path)).is_file():
            raise TaskError(f"Source PDF does not exist: {file_path}")
        if not self.adapter and not self.api_key:
            raise TaskError("LlamaCloudSplitTask requires api_key or injected adapter.")
        if not self.configuration_id and not self.categories:
            raise TaskError("LlamaCloudSplitTask requires categories or configuration_id.")

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Run split fan-out for a root/source document."""
        self.initialize_context(context)
        try:
            self.validate_required_fields(context)
            if not self.enabled:
                context.setdefault("data", {})["split_result"] = {"status": "skipped"}
                return context

            with connect(self.config_manager) as conn:
                documents = DocumentRepository(conn)
                document = documents.get(str(context["document_id"]))
                if document is None:
                    raise TaskError(f"Document not found: {context['document_id']}")
                if document.get("parent_document_id"):
                    context.setdefault("data", {})["split_result"] = {"status": "skipped_child"}
                    return context

                split_result = self._get_adapter().split_pdf(str(context["file_path"]), self.categories)
                if not split_result.segments:
                    context.setdefault("data", {})["split_result"] = {
                        "status": "no_segments",
                        "provider_job_id": split_result.provider_job_id,
                    }
                    return context

                self._validate_all_segment_pages(str(context["file_path"]), split_result.segments)
                source_artifact = self._ensure_source_artifact(documents, document, context)
                parent_metadata = json_loads(document.get("metadata_json"), {})
                parent_metadata["split_result"] = {
                    "provider": "llamacloud_split",
                    "provider_job_id": split_result.provider_job_id,
                    "status": split_result.status,
                    "categories": self.categories,
                    "allow_uncategorized": self.allow_uncategorized,
                    "raw_response": split_result.raw_response,
                }
                documents.update_metadata(document["id"], parent_metadata)

                child_ids = self._create_children(
                    documents=documents,
                    document=document,
                    context=context,
                    split_result=split_result,
                    source_artifact=source_artifact,
                )
                documents.update_status(document["id"], "split_completed")
                BatchRepository(conn).recompute_counts(str(document["batch_id"]))
                AuditRepository(conn).append(
                    event_type="split_completed",
                    event={
                        "provider_job_id": split_result.provider_job_id,
                        "child_document_ids": child_ids,
                        "segments": len(child_ids),
                    },
                    batch_id=str(document["batch_id"]),
                    document_id=str(document["id"]),
                )

            context["split_children"] = child_ids
            context["split_provider_job_id"] = split_result.provider_job_id
            context["fan_out_start_task_index"] = int(context.get("current_task_index") or 0) + 1
            context["pipeline_state"] = "fan_out"
            context.setdefault("data", {})["split_result"] = {
                "status": "split_completed",
                "provider_job_id": split_result.provider_job_id,
                "children": child_ids,
            }
            return context
        except TaskError as exc:
            self.logger.error("Split task failed: %s", exc)
            self.register_error(context, exc)
            return context
        except Exception as exc:
            self.logger.exception("Unexpected split task failure")
            self.register_error(context, TaskError(f"Unexpected split error: {exc}"))
            return context

    def _get_adapter(self) -> Any:
        """Return an injected or real LlamaCloud Split adapter."""
        if self.adapter is not None:
            return self.adapter
        return LlamaCloudSplitAdapter(
            api_key=self.api_key,
            project_id=self.project_id,
            organization_id=self.organization_id,
            configuration_id=self.configuration_id,
            allow_uncategorized=self.allow_uncategorized,
            polling_interval_seconds=self.poll_interval_seconds,
            timeout_seconds=self.timeout_seconds,
        )

    @staticmethod
    def _validate_all_segment_pages(source_pdf_path: str, segments: list[SplitSegment]) -> None:
        """Validate all requested split pages before writing child files."""
        page_count = len(PdfReader(source_pdf_path).pages)
        for segment in segments:
            invalid_pages = [page for page in segment.pages if page < 1 or page > page_count]
            if invalid_pages:
                raise TaskError(
                    f"Split pages {invalid_pages} are outside source PDF page range 1-{page_count}."
                )

    @staticmethod
    def _ensure_source_artifact(
        documents: DocumentRepository,
        document: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Register the root source PDF as a source artifact when needed."""
        source_path = str(Path(str(context["file_path"])).resolve())
        for file_record in documents.list_files(str(document["id"])):
            if (
                file_record.get("file_type") == "source_original"
                and str(Path(str(file_record["file_path"])).resolve()) == source_path
            ):
                return file_record
        return documents.add_file(
            document_id=str(document["id"]),
            file_type="source_original",
            file_path=source_path,
            metadata={
                "source": context.get("source"),
                "original_filename": context.get("original_filename") or document.get("original_filename"),
            },
        )

    def _create_children(
        self,
        *,
        documents: DocumentRepository,
        document: dict[str, Any],
        context: dict[str, Any],
        split_result: SplitResult,
        source_artifact: dict[str, Any],
    ) -> list[str]:
        """Create child PDFs, child document records, and split artifacts."""
        child_ids: list[str] = []
        source_pdf_path = str(context["file_path"])
        source_filename = str(context.get("original_filename") or document.get("original_filename") or "source.pdf")
        base_name = Path(sanitize_filename(source_filename)).stem
        inherited_context = context.get("metadata", {}).get("inherited_context") if isinstance(context.get("metadata"), dict) else None

        for index, segment in enumerate(split_result.segments, start=1):
            category = sanitize_filename(segment.category or "uncategorized")
            output_base = f"{base_name}_segment_{index:03d}_{category}_p{segment.page_start}-{segment.page_end}"
            if self.split_dir is None:
                raise TaskError("LlamaCloudSplitTask requires split_dir.")
            output_path = generate_unique_filepath(self.split_dir, output_base, ".pdf")
            create_split_pdf(source_pdf_path, str(output_path), segment.pages)

            child_filename = output_path.name
            child_metadata: dict[str, Any] = {
                "root_document_id": document["id"],
                "source_original_filename": source_filename,
                "source_file_path": str(Path(source_pdf_path).resolve()),
                "source_file_artifact_id": source_artifact.get("id"),
                "split_provider_job_id": split_result.provider_job_id,
                "split_segment_index": index - 1,
                "split_pages": segment.pages,
                "split_category": segment.category,
                "split_confidence": segment.confidence,
                "split_raw_segment": segment.metadata.get("raw_segment"),
            }
            if inherited_context is not None:
                child_metadata["inherited_context"] = inherited_context

            child = documents.create_child(
                batch_id=str(document["batch_id"]),
                parent_document_id=str(document["id"]),
                file_path=str(output_path.resolve()),
                original_filename=child_filename,
                document_type=segment.category,
                page_start=segment.page_start,
                page_end=segment.page_end,
                split_category=segment.category,
                split_confidence=segment.confidence,
                status="queued",
                metadata=child_metadata,
            )
            documents.add_file(
                document_id=str(child["id"]),
                file_type="split_pdf",
                file_path=str(output_path.resolve()),
                metadata=child_metadata,
            )
            child_ids.append(str(child["id"]))

        return child_ids
