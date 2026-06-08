from pathlib import Path

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from modules.services.processing_state_service import (
    build_pipeline_snapshot,
    snapshot_from_batch,
    ProcessingStateService,
)
from test.helpers_sqlite import TempConfig


def _config(tmp_path: Path) -> TempConfig:
    return TempConfig(
        tmp_path / "app.sqlite3",
        {
            "tasks": {
                "assign_nanoid": {
                    "module": "standard_step.context.assign_nanoid",
                    "class": "AssignNanoidTask",
                    "params": {"secret_token": "hidden"},
                },
                "split_pdf": {
                    "module": "standard_step.split.llamacloud_split",
                    "class": "LlamaCloudSplitTask",
                    "params": {"api_key": "hidden", "split_dir": str(tmp_path / "split")},
                },
                "extract_invoice": {
                    "module": "standard_step.extraction.extract_pdf_v2",
                    "class": "ExtractPdfV2Task",
                    "params": {"api_key": "hidden"},
                },
                "review_gate": {
                    "module": "standard_step.review.review_gate",
                    "class": "ReviewGateTask",
                },
                "store_json": {
                    "module": "standard_step.storage.store_metadata_as_json",
                    "class": "StoreMetadataAsJson",
                    "on_error": "continue",
                },
            },
            "pipeline": ["assign_nanoid", "split_pdf", "extract_invoice", "review_gate", "store_json"],
        },
    )


def test_build_pipeline_snapshot_excludes_params_and_classifies_steps(tmp_path):
    config = _config(tmp_path)

    snapshot = build_pipeline_snapshot(config)

    assert snapshot["step_count"] == 5
    assert [step["key"] for step in snapshot["steps"]] == [
        "assign_nanoid",
        "split_pdf",
        "extract_invoice",
        "review_gate",
        "store_json",
    ]
    assert [step["category"] for step in snapshot["steps"]] == [
        "context",
        "split",
        "extract",
        "review",
        "storage",
    ]
    assert all("params" not in step for step in snapshot["steps"])
    assert snapshot["steps"][-1]["on_error"] == "continue"


def test_snapshot_from_batch_falls_back_for_historical_batches(tmp_path):
    config = _config(tmp_path)
    initialize_database(config)

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch_with_documents(
            source="web",
            files=[{"file_path": str(tmp_path / "invoice.pdf"), "original_filename": "invoice.pdf"}],
            metadata={"uploaded_by": "operator"},
        )
        snapshot = snapshot_from_batch(created["batch"], config)

    assert snapshot["fallback"] is True
    assert snapshot["source"] == "active_config_fallback"
    assert snapshot["steps"][0]["key"] == "assign_nanoid"


def test_batch_processing_state_keeps_original_snapshot_after_config_change(tmp_path):
    config = _config(tmp_path)
    initialize_database(config)
    original_snapshot = build_pipeline_snapshot(config)

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch_with_documents(
            source="web",
            files=[{"file_path": str(tmp_path / "invoice.pdf"), "original_filename": "invoice.pdf"}],
            metadata={"pipeline_snapshot": original_snapshot},
        )
        config._values["pipeline"] = ["review_gate", "store_json"]
        payload = ProcessingStateService(config, conn).get_batch_state(created["batch"]["id"])

    assert payload is not None
    assert [step["key"] for step in payload["pipeline_snapshot"]["steps"]] == [
        "assign_nanoid",
        "split_pdf",
        "extract_invoice",
        "review_gate",
        "store_json",
    ]


def test_processing_state_aggregates_running_failed_and_paused_steps(tmp_path):
    config = _config(tmp_path)
    initialize_database(config)
    snapshot = build_pipeline_snapshot(config)

    with connect(config) as conn:
        service = BatchService(conn)
        created = service.create_ingestion_batch_with_documents(
            source="web",
            files=[
                {"file_path": str(tmp_path / "a.pdf"), "original_filename": "a.pdf", "document_id": "doc-a"},
                {"file_path": str(tmp_path / "b.pdf"), "original_filename": "b.pdf", "document_id": "doc-b"},
                {"file_path": str(tmp_path / "c.pdf"), "original_filename": "c.pdf", "document_id": "doc-c"},
            ],
            metadata={"pipeline_snapshot": snapshot},
            status="processing",
        )
        runs = TaskRunRepository(conn)
        documents = DocumentRepository(conn)

        for document in created["documents"]:
            run = runs.create_started(
                batch_id=created["batch"]["id"],
                document_id=document["id"],
                task_key="assign_nanoid",
                task_index=0,
                module_name="standard_step.context.assign_nanoid",
                class_name="AssignNanoidTask",
            )
            runs.mark_completed(run["id"])

        running = runs.create_started(
            batch_id=created["batch"]["id"],
            document_id="doc-a",
            task_key="extract_invoice",
            task_index=2,
            module_name="standard_step.extraction.extract_pdf_v2",
            class_name="ExtractPdfV2Task",
        )
        failed = runs.create_started(
            batch_id=created["batch"]["id"],
            document_id="doc-b",
            task_key="extract_invoice",
            task_index=2,
            module_name="standard_step.extraction.extract_pdf_v2",
            class_name="ExtractPdfV2Task",
        )
        runs.mark_failed(failed["id"], "boom")
        paused = runs.create_started(
            batch_id=created["batch"]["id"],
            document_id="doc-c",
            task_key="review_gate",
            task_index=3,
            module_name="standard_step.review.review_gate",
            class_name="ReviewGateTask",
        )
        runs.mark_paused(paused["id"])
        documents.update_status("doc-c", "review_required")

        payload = ProcessingStateService(config, conn).get_batch_state(created["batch"]["id"])

    assert payload is not None
    states = {step["key"]: step for step in payload["aggregate_step_states"]}
    assert states["assign_nanoid"]["state"] == "completed"
    assert states["extract_invoice"]["state"] == "failed"
    assert states["review_gate"]["state"] == "paused"
    doc_a = next(document for document in payload["documents"] if document["id"] == "doc-a")
    assert doc_a["current_step"]["key"] == "extract_invoice"
    assert doc_a["progress_percent"] > 0
    assert running["status"] == "running"


def test_processing_state_handles_split_fan_out_applicability(tmp_path):
    config = _config(tmp_path)
    initialize_database(config)
    snapshot = build_pipeline_snapshot(config)

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch_with_documents(
            source="web",
            files=[{"file_path": str(tmp_path / "source.pdf"), "original_filename": "source.pdf", "document_id": "root"}],
            metadata={"pipeline_snapshot": snapshot},
            status="processing",
        )
        documents = DocumentRepository(conn)
        documents.create_child(
            batch_id=created["batch"]["id"],
            parent_document_id="root",
            file_path=str(tmp_path / "child.pdf"),
            original_filename="child.pdf",
            status="processing",
        )
        runs = TaskRunRepository(conn)
        split_run = runs.create_started(
            batch_id=created["batch"]["id"],
            document_id="root",
            task_key="split_pdf",
            task_index=1,
            module_name="standard_step.split.llamacloud_split",
            class_name="LlamaCloudSplitTask",
        )
        runs.mark_completed(split_run["id"])
        child = documents.list_children("root")[0]
        runs.create_started(
            batch_id=created["batch"]["id"],
            document_id=child["id"],
            task_key="extract_invoice",
            task_index=2,
            module_name="standard_step.extraction.extract_pdf_v2",
            class_name="ExtractPdfV2Task",
        )

        payload = ProcessingStateService(config, conn).get_batch_state(created["batch"]["id"])

    assert payload is not None
    root = next(document for document in payload["documents"] if document["id"] == "root")
    child_payload = next(document for document in payload["documents"] if document["parent_document_id"] == "root")
    root_states = {step["key"]: step["state"] for step in root["task_states"]}
    child_states = {step["key"]: step["state"] for step in child_payload["task_states"]}
    assert root_states["split_pdf"] == "completed"
    assert root_states["extract_invoice"] == "skipped"
    assert child_states["split_pdf"] == "skipped"
    assert child_states["extract_invoice"] == "running"
