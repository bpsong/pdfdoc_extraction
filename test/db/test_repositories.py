from pathlib import Path

from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import (
    AppSettingsRepository,
    AuditRepository,
    BatchRepository,
    ConfigVersionRepository,
    DocumentRepository,
    ExtractionRepository,
    ReviewRepository,
    TaskRunRepository,
)


class TempConfig:
    def __init__(self, db_path: Path) -> None:
        self._config_path = db_path.parent / "config.yaml"
        self._values = {"database.path": str(db_path)}

    def get(self, key, default=None):
        return self._values.get(key, default)


def test_repositories_cover_core_state_models(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)

    with connect(config) as conn:
        batches = BatchRepository(conn)
        documents = DocumentRepository(conn)
        task_runs = TaskRunRepository(conn)
        extractions = ExtractionRepository(conn)
        reviews = ReviewRepository(conn)
        audits = AuditRepository(conn)
        settings = AppSettingsRepository(conn)
        versions = ConfigVersionRepository(conn)

        batch = batches.create(source="web", original_filename="invoice.pdf")
        document = documents.create_root(
            batch_id=batch["id"],
            file_path=str(tmp_path / "invoice.pdf"),
            original_filename="invoice.pdf",
        )
        documents.add_file(document_id=document["id"], file_type="original_pdf", file_path=document["file_path"])
        child = documents.create_child(
            batch_id=batch["id"],
            parent_document_id=document["id"],
            file_path=str(tmp_path / "child.pdf"),
            page_start=1,
            page_end=2,
        )

        task_run = task_runs.create_started(
            batch_id=batch["id"],
            document_id=document["id"],
            task_key="extract",
            task_index=0,
            module_name="standard_step.extraction.extract_pdf_v2",
            class_name="ExtractPdfV2Task",
            input_data={"id": document["id"]},
        )
        task_runs.mark_completed(task_run["id"], {"ok": True})

        result = extractions.save_result(
            document_id=document["id"],
            task_run_id=task_run["id"],
            provider="llamacloud",
            provider_job_id="job-1",
            data={"supplier": "Acme"},
        )
        extractions.save_fields(
            document_id=document["id"],
            extraction_result_id=result["id"],
            fields=[
                {
                    "field_key": "supplier",
                    "field_alias": "Supplier",
                    "extracted_value": "Acme",
                    "confidence": 0.9,
                }
            ],
        )
        extractions.apply_corrections(document["id"], {"supplier": "Acme Pte Ltd"})

        review = reviews.create_review_item(
            batch_id=batch["id"],
            document_id=document["id"],
            queue_name="default_review",
            reason="low_confidence",
            scope="field",
        )
        reviews.claim(review["id"], "operator")
        assert reviews.get_lock(review["id"])["locked_by"] == "operator"
        reviews.complete(review["id"], "operator")

        audit = audits.append(
            event_type="review_completed",
            event={"field": "supplier"},
            batch_id=batch["id"],
            document_id=document["id"],
            review_item_id=review["id"],
            user="operator",
        )
        settings.set("page_size", 25)
        draft = versions.create_draft(
            config_type="pipeline",
            name="default",
            content_text="pipeline: []\n",
            created_by="admin",
        )
        published = versions.publish(draft["id"])

        recomputed = batches.recompute_counts(batch["id"])

    assert child["parent_document_id"] == document["id"]
    assert task_runs.list_by_document(document["id"])[0]["status"] == "completed"
    assert json_loads(extractions.get_fields(document["id"])[0]["final_value_json"]) == "Acme Pte Ltd"
    assert audits.list_for_document(document["id"])[0]["id"] == audit["id"]
    assert settings.get("page_size") == 25
    assert published and published["status"] == "published"
    assert versions.get_active("pipeline", "default")["id"] == draft["id"]
    assert recomputed and recomputed["total_documents"] == 2
