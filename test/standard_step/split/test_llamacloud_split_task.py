from pathlib import Path

from pypdf import PdfReader, PdfWriter

from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository
from modules.services.batch_service import BatchService
from standard_step.housekeeping.cleanup_task import CleanupTask
from standard_step.split.llamacloud_split import LlamaCloudSplitTask, create_split_pdf
from standard_step.split.llamacloud_split_adapter import SplitResult, SplitSegment
from test.helpers_sqlite import TempConfig


def _write_pdf(path: Path, page_count: int) -> None:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as file_obj:
        writer.write(file_obj)


class FakeSplitAdapter:
    def split_pdf(self, file_path, categories):
        return SplitResult(
            provider_job_id="spl-1",
            status="completed",
            segments=[
                SplitSegment(
                    category="invoice",
                    confidence="high",
                    pages=[1, 2],
                    page_start=1,
                    page_end=2,
                    metadata={"raw_segment": {"pages": [1, 2]}},
                ),
                SplitSegment(
                    category="delivery_order",
                    confidence="medium",
                    pages=[3, 4],
                    page_start=3,
                    page_end=4,
                    metadata={"raw_segment": {"pages": [3, 4]}},
                ),
            ],
            raw_response={"id": "spl-1"},
        )


def test_create_split_pdf_copies_requested_pages(tmp_path):
    source = tmp_path / "source.pdf"
    output = tmp_path / "child.pdf"
    _write_pdf(source, 4)

    create_split_pdf(str(source), str(output), [2, 4])

    assert output.exists()
    assert len(PdfReader(str(output)).pages) == 2


def test_llamacloud_split_task_creates_children_and_artifacts(tmp_path):
    source = tmp_path / "bundle.pdf"
    split_dir = tmp_path / "split"
    _write_pdf(source, 4)
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(source),
            original_filename="bundle.pdf",
        )

    task = LlamaCloudSplitTask(
        config_manager=config,
        enabled=True,
        adapter=FakeSplitAdapter(),
        categories=[{"name": "invoice"}],
        split_dir=str(split_dir),
    )
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "file_path": str(source),
        "original_filename": "bundle.pdf",
        "source": "web",
        "current_task_index": 0,
    }

    result = task.run(context)

    assert result["pipeline_state"] == "fan_out"
    assert result["fan_out_start_task_index"] == 1
    assert len(result["split_children"]) == 2

    with connect(config) as conn:
        documents = DocumentRepository(conn)
        parent = documents.get(created["document"]["id"])
        children = documents.list_children(created["document"]["id"])
        parent_files = documents.list_files(created["document"]["id"])
        child_files = [documents.list_files(child["id"])[0] for child in children]

    assert parent["status"] == "split_completed"
    assert any(file_record["file_type"] == "source_original" for file_record in parent_files)
    assert [child["page_start"] for child in children] == [1, 3]
    assert [child["page_end"] for child in children] == [2, 4]
    assert [child["split_category"] for child in children] == ["invoice", "delivery_order"]
    assert all(file_record["file_type"] == "split_pdf" for file_record in child_files)
    assert all(Path(file_record["file_path"]).exists() for file_record in child_files)
    assert all(len(PdfReader(file_record["file_path"]).pages) == 2 for file_record in child_files)

    child_metadata = json_loads(children[0]["metadata_json"], {})
    assert child_metadata["root_document_id"] == created["document"]["id"]
    assert child_metadata["source_original_filename"] == "bundle.pdf"
    assert child_metadata["split_pages"] == [1, 2]


def test_cleanup_preserves_registered_split_pdf(tmp_path):
    split_pdf = tmp_path / "split.pdf"
    _write_pdf(split_pdf, 1)
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(tmp_path / "source.pdf"),
            original_filename="source.pdf",
        )
        documents = DocumentRepository(conn)
        child = documents.create_child(
            batch_id=created["batch"]["id"],
            parent_document_id=created["document"]["id"],
            file_path=str(split_pdf),
        )
        documents.add_file(
            document_id=child["id"],
            file_type="split_pdf",
            file_path=str(split_pdf),
        )

    cleanup = CleanupTask(config_manager=config, processing_dir=tmp_path)
    cleanup.run({"document_id": child["id"], "file_path": str(split_pdf), "id": child["id"]})

    assert split_pdf.exists()
