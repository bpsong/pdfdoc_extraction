"""Shared local split materialization with compensation and artifact registration."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from modules.config_protocol import ConfigProvider
from modules.db.connection import json_loads, transaction
from modules.db.repositories import DocumentRepository, BatchRepository
from modules.exceptions import TaskError
from modules.services.artifact_service import register_document_artifact
from modules.services.workflow_state_service import WorkflowStateService
from modules.utils import reserve_unique_filepath, release_reserved_filepath, sanitize_filename
from modules.split_models import SplitResult
from pypdf import PdfReader, PdfWriter


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



class SplitExecutionService:
    """Create a complete set of split children using a caller's transaction."""

    def __init__(self, config_manager: ConfigProvider, split_dir: Path, task_key: str, pdf_writer: Callable[[str, str, list[int]], None]) -> None:
        self.config_manager = config_manager
        self.split_dir = split_dir
        self._task_key = task_key
        self.pdf_writer = pdf_writer
        self.logger = logging.getLogger(__name__)

    def task_key(self, context: dict[str, Any]) -> str:
        return self._task_key

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
        reserved_paths: list[Path] = []
        source_pdf_path = str(context["file_path"])
        source_filename = str(context.get("original_filename") or document.get("original_filename") or "source.pdf")
        base_name = Path(sanitize_filename(source_filename)).stem
        inherited_context = context.get("metadata", {}).get("inherited_context") if isinstance(context.get("metadata"), dict) else None

        try:
            for index, segment in enumerate(split_result.segments, start=1):
                category = sanitize_filename(segment.category or "uncategorized")
                output_base = f"{base_name}_segment_{index:03d}_{category}_p{segment.page_start}-{segment.page_end}"
                if self.split_dir is None:
                    raise TaskError("Split materialization requires split_dir.")
                output_path = reserve_unique_filepath(self.split_dir, output_base, ".pdf")
                reserved_paths.append(output_path)
                self.pdf_writer(source_pdf_path, str(output_path), segment.pages)

                child_filename = output_path.name
                child_metadata: dict[str, Any] = {
                    "task_key": self.task_key(context),
                    "root_document_id": json_loads(document.get("metadata_json"), {}).get("root_document_id") or document["id"],
                    "manual_split_decision_id": context.get("manual_split_decision_id"),
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
                continued_failures = context.get("continued_failures")
                if isinstance(continued_failures, list) and continued_failures:
                    child_metadata["continued_failures"] = continued_failures

                with transaction(documents.conn):
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
                        pipeline_template_id=document.get("pipeline_template_id"),
                        pipeline_version_id=document.get("pipeline_version_id"),
                    )
                    register_document_artifact(
                        self.config_manager, {"document_id": str(child["id"])}, connection=documents.conn,
                        file_type="split_pdf",
                        file_path=str(output_path.resolve()),
                        metadata=child_metadata,
                    )
                    child_ids.append(str(child["id"]))
        except Exception:
            self._rollback_partial_children(
                documents=documents,
                document=document,
                child_ids=child_ids,
                reserved_paths=reserved_paths,
            )
            raise

        return child_ids

    def _rollback_partial_children(
        self,
        *,
        documents: DocumentRepository,
        document: dict[str, Any],
        child_ids: list[str],
        reserved_paths: list[Path],
    ) -> None:
        """Compensate child rows and files created before a split failure."""
        for child_id in reversed(child_ids):
            try:
                documents.delete_pending_child(child_id)
            except Exception:
                self.logger.exception("Failed to remove partial split child %s", child_id)

        for output_path in reversed(reserved_paths):
            if not release_reserved_filepath(output_path):
                self.logger.warning("Failed to remove partial split output")

        remaining_children = documents.list_children(str(document["id"]))
        if not remaining_children:
            return

        for child in remaining_children:
            if child.get("status") not in {"completed", "failed"}:
                WorkflowStateService(documents.conn).transition_document(
                    str(child["id"]), "failed", reason="split_failed"
                )
        WorkflowStateService(documents.conn).transition_document(
            str(document["id"]), "failed", reason="split_failed"
        )
        BatchRepository(documents.conn).recompute_counts(str(document["batch_id"]))
