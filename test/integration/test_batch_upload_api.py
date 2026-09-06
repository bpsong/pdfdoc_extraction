from pathlib import Path
from typing import Any
import pytest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.file_processor import FileProcessor
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.upload_receiver import MAX_PART_HEADER_BYTES
from modules.services.upload_receiver import reconcile_upload_files
from modules.services.upload_storage_lock import UploadStorageBusy, upload_storage_access


class TempConfig:
    """Config stub for batch upload API tests."""

    def __init__(self, root: Path) -> None:
        self._config_path = root / "config.yaml"
        self.pipeline_version_id = ""
        self._values = {
            "database.path": str(root / "app.sqlite3"),
            "database.run_migrations_on_startup": True,
            "web.upload_dir": str(root / "web_upload"),
            "watch_folder.dir": str(root / "watch"),
            "watch_folder.processing_dir": str(root / "processing"),
            "watch_folder.validate_pdf_header": True,
            "pipeline_secrets": {"test-api": "runtime-secret"},
            "tasks": {
                "extract_invoice": {
                    "module": "standard_step.extraction.extract_pdf",
                    "class": "ExtractPdfTask",
                    "params": {"api_key": "secret"},
                },
                "store_json": {
                    "module": "standard_step.storage.store_metadata_as_json",
                    "class": "StoreMetadataAsJson",
                },
            },
            "pipeline": ["extract_invoice", "store_json"],
        }
        for key in ("web.upload_dir", "watch_folder.dir", "watch_folder.processing_dir"):
            Path(self._values[key]).mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def get_all(self) -> dict[str, Any]:
        return dict(self._values)


def test_upload_receipt_retry_and_conflicting_content(tmp_path, monkeypatch):
    client, config, _ = build_client(tmp_path, monkeypatch)
    key = "8648d58e-0e8c-4677-b4af-a13f63067117"
    def submit(content):
        return client.post("/api/batches/upload", headers={"Idempotency-Key": key},
            data={"pipeline_version_id": config.pipeline_version_id},
            files=[("files", ("a.pdf", content, "application/pdf"))])
    assert client.get(f"/api/upload-submissions/{key}").json() == {"status": "unknown"}
    first = submit(b"%PDF-first")
    assert first.status_code == 200
    retry = submit(b"%PDF-first")
    assert retry.json() == first.json()
    assert submit(b"%PDF-changed").status_code == 400
    assert client.get(f"/api/upload-submissions/{key}").json() == {
        "status": "accepted", "batch_id": first.json()["batch_id"]}
    with connect(config) as conn:
        for table in ("batches", "documents", "processing_jobs", "upload_submissions"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
        from modules.services.upload_submission_service import submission_status
        assert submission_status(conn, "different-user", key) == {"status": "unknown"}
    root = Path(config.get("watch_folder.processing_dir"))
    assert len(list(root.glob("web-upload-*.pdf"))) == 1
    assert not list(root.rglob("*.upload"))


def test_simultaneous_submission_retries_create_one_batch(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    client, config, _ = build_client(tmp_path, monkeypatch)
    def submit(_):
        return client.post("/api/batches/upload",
            headers={"Idempotency-Key": "66f1af23-aed6-4cb5-9ed5-89d2b5708284"},
            data={"pipeline_version_id": config.pipeline_version_id},
            files=[("files", ("same.pdf", b"%PDF-concurrent", "application/pdf"))])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()
    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM processing_jobs").fetchone()[0] == 1


def test_receipt_failure_rolls_back_jobs_and_files(tmp_path, monkeypatch):
    from modules.db.repositories import UploadSubmissionRepository
    import sqlite3
    client, config, _ = build_client(tmp_path, monkeypatch)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic receipt failure")
    monkeypatch.setattr(UploadSubmissionRepository, "record", fail)
    response = client.post("/api/batches/upload",
        headers={"Idempotency-Key": "66f1af23-aed6-4cb5-9ed5-89d2b5708284"},
        data={"pipeline_version_id": config.pipeline_version_id},
        files=[("files", ("same.pdf", b"%PDF-rollback", "application/pdf"))])
    assert response.status_code == 500
    with connect(config) as conn:
        for table in ("batches", "documents", "processing_jobs", "upload_submissions"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert not list(Path(config.get("watch_folder.processing_dir")).rglob("*.pdf"))


class FakeWorkflowManager:
    """Workflow manager stub that records trigger calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def trigger_workflow_for_file(self, **kwargs: Any) -> bool:
        self.calls.append(kwargs)
        return True


def build_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, TempConfig, FakeWorkflowManager]:
    """Build a test client with real SQLite state and fake workflow execution."""

    config = TempConfig(tmp_path)
    initialize_database(config)
    with connect(config) as conn:
        templates = PipelineTemplateService(
            conn, configured_secret_aliases={"test-api"}
        )
        created = templates.create_template(
            template_key="batch-upload-test",
            name="Batch upload test",
            initial_definition={
                "schema_version": 1,
                "pipeline": ["extract"],
                "tasks": {
                    "extract": {
                        "module": "standard_step.extraction.extract_pdf",
                        "class": "ExtractPdfTask",
                        "params": {
                            "api_key": {"$secret": "test-api"},
                            "fields": {
                                "supplier": {
                                    "alias": "Supplier",
                                    "type": "str",
                                }
                            },
                        },
                    }
                },
            },
            user="admin",
        )
        published = templates.publish(
            created["template"]["id"], expected_revision=1, user="admin"
        )
        templates.update_template(
            created["template"]["id"], status="active", user="admin"
        )
        config.pipeline_version_id = published["version"]["id"]
    workflow = FakeWorkflowManager()
    processor = FileProcessor(config, lambda func, *args, **kwargs: func(*args, **kwargs), workflow)
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, workflow, processor

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    return TestClient(app), config, workflow


def test_batch_upload_api_creates_one_batch_for_multiple_pdfs(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("invoice_a.pdf", b"%PDF-1.4\ninvoice-a", "application/pdf")),
            ("files", ("invoice_b.pdf", b"%PDF-1.4\ninvoice-b", "application/pdf")),
        ],
        data={"pipeline_version_id": config.pipeline_version_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert len(payload["document_ids"]) == 2

    with connect(config) as conn:
        batches = conn.execute("SELECT * FROM batches").fetchall()
        documents = conn.execute("SELECT * FROM documents ORDER BY original_filename").fetchall()
        source_files = conn.execute(
            "SELECT * FROM document_files WHERE file_type = 'source_original'"
        ).fetchall()

    assert len(batches) == 1
    assert batches[0]["id"] == payload["batch_id"]
    assert batches[0]["source"] == "web"
    assert batches[0]["total_documents"] == 2
    metadata = json_loads(batches[0]["metadata_json"])
    assert metadata["file_count"] == 2
    assert batches[0]["pipeline_version_id"] == config.pipeline_version_id
    assert all(
        document["pipeline_version_id"] == config.pipeline_version_id
        for document in documents
    )
    assert payload["pipeline"]["step_count"] == 1
    assert [document["original_filename"] for document in documents] == ["invoice_a.pdf", "invoice_b.pdf"]
    assert {document["id"] for document in documents} == set(payload["document_ids"])
    assert len(source_files) == 2
    assert all(Path(document["file_path"]).exists() for document in documents)
    assert all(Path(document["file_path"]).name.startswith("web-upload-") for document in documents)
    assert not list((Path(config.get("watch_folder.processing_dir")) / ".upload_staging").glob("*.upload"))
    assert workflow.calls == []
    with connect(config) as conn:
        jobs = conn.execute(
            "SELECT * FROM processing_jobs WHERE batch_id = ? ORDER BY created_at",
            (payload["batch_id"],),
        ).fetchall()
    assert len(jobs) == 2
    assert {job["document_id"] for job in jobs} == set(payload["document_ids"])
    assert {job["status"] for job in jobs} == {"queued"}


def test_batch_upload_api_rejects_cookie_auth_without_csrf_token(tmp_path, monkeypatch):
    client, _, _ = build_client(tmp_path, monkeypatch)
    client.cookies.set("access_token", "browser-token")

    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("invoice_a.pdf", b"%PDF-1.4\ninvoice-a", "application/pdf")),
        ],
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF token missing or invalid"


def test_batch_upload_api_accepts_cookie_auth_with_csrf_token(tmp_path, monkeypatch):
    client, config, _ = build_client(tmp_path, monkeypatch)
    client.cookies.set("access_token", "browser-token")
    client.cookies.set("csrf_token", "csrf-test-token")

    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("invoice_a.pdf", b"%PDF-1.4\ninvoice-a", "application/pdf")),
        ],
        data={"pipeline_version_id": config.pipeline_version_id},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_batch_upload_api_rejects_invalid_pdf_without_persisting_state(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("not-a-pdf.txt", b"%PDF-1.4\ntext", "text/plain")),
        ],
        data={"pipeline_version_id": config.pipeline_version_id},
    )

    assert response.status_code == 400
    with connect(config) as conn:
        batch_count = conn.execute("SELECT COUNT(*) AS count FROM batches").fetchone()["count"]
        document_count = conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]

    assert batch_count == 0
    assert document_count == 0
    assert workflow.calls == []


def test_batch_upload_api_rejects_oversized_request_before_persisting_state(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)
    config._values["web.max_upload_request_mb"] = 1

    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("large.pdf", b"%PDF-" + (b"A" * (1024 * 1024)), "application/pdf")),
        ],
        data={"pipeline_version_id": config.pipeline_version_id},
    )

    assert response.status_code == 413
    assert "request is too large" in response.json()["detail"]
    with connect(config) as conn:
        batch_count = conn.execute("SELECT COUNT(*) AS count FROM batches").fetchone()["count"]
        document_count = conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]

    assert batch_count == 0
    assert document_count == 0
    assert workflow.calls == []


def test_batch_upload_api_rejects_oversized_file_without_persisting_state(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)
    config._values["web.max_upload_mb"] = 1
    config._values["web.max_upload_request_mb"] = 5

    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("large.pdf", b"%PDF-" + (b"A" * (1024 * 1024)), "application/pdf")),
        ],
        data={"pipeline_version_id": config.pipeline_version_id},
    )

    assert response.status_code == 413
    assert "too large" in response.json()["detail"]
    with connect(config) as conn:
        batch_count = conn.execute("SELECT COUNT(*) AS count FROM batches").fetchone()["count"]
        document_count = conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]

    assert batch_count == 0
    assert document_count == 0
    assert workflow.calls == []


def test_batch_upload_api_rejects_too_many_files_without_persisting_state(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)
    config._values["web.max_upload_files"] = 1
    config._values["web.max_upload_request_mb"] = 5

    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("invoice_a.pdf", b"%PDF-1.4\ninvoice-a", "application/pdf")),
            ("files", ("invoice_b.pdf", b"%PDF-1.4\ninvoice-b", "application/pdf")),
        ],
        data={"pipeline_version_id": config.pipeline_version_id},
    )

    assert response.status_code == 413
    assert "Too many files" in response.json()["detail"]
    with connect(config) as conn:
        batch_count = conn.execute("SELECT COUNT(*) AS count FROM batches").fetchone()["count"]
        document_count = conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]

    assert batch_count == 0
    assert document_count == 0
    assert workflow.calls == []


def test_batch_upload_api_removes_finalized_files_when_database_commit_fails(
    tmp_path, monkeypatch
):
    client, config, workflow = build_client(tmp_path, monkeypatch)

    def fail_create_batch(*args, **kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(IngestionAssignmentService, "create_batch", fail_create_batch)
    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("invoice.pdf", b"%PDF-1.4\ninvoice", "application/pdf")),
        ],
        data={"pipeline_version_id": config.pipeline_version_id},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to accept upload batch"
    processing = Path(config.get("watch_folder.processing_dir"))
    assert not list(processing.glob("web-upload-*.pdf"))
    assert not list((processing / ".upload_staging").glob("*.upload"))
    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM processing_jobs").fetchone()[0] == 0
    assert workflow.calls == []


def test_batch_upload_api_never_buffers_the_complete_request(
    tmp_path, monkeypatch
):
    client, config, _ = build_client(tmp_path, monkeypatch)

    async def fail_if_body_is_buffered(self):
        raise AssertionError("upload route must stream instead of calling request.body()")

    monkeypatch.setattr(Request, "body", fail_if_body_is_buffered)
    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("invoice.pdf", b"%PDF-1.4\ninvoice", "application/pdf")),
        ],
        data={"pipeline_version_id": config.pipeline_version_id},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"


@pytest.mark.parametrize("oversized_header", [False, True])
def test_malformed_batch_upload_creates_no_partial_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, oversized_header: bool
) -> None:
    client, config, workflow = build_client(tmp_path, monkeypatch)
    body = (
        f'--a\r\nContent-Disposition: form-data; name="pipeline_version_id"\r\n\r\n{config.pipeline_version_id}'
        '\r\n--a\r\nContent-Disposition: form-data; name="files"; filename="one.pdf"'
        '\r\n\r\n%PDF-one\r\n--a\r\nContent-Disposition: form-data; name="files"; filename="two.pdf"'
    ).encode()
    if oversized_header:
        body += b'\r\nX-Large: ' + b'x' * MAX_PART_HEADER_BYTES
        body += b'\r\n\r\n%PDF-two\r\n--a--\r\n'
    else:
        body += b'\r\n\r\n%PDF-truncated'
    response = client.post(
        "/api/batches/upload", content=body,
        headers={"Content-Type": "multipart/form-data; boundary=a"},
    )
    assert response.status_code == (413 if oversized_header else 400)
    with connect(config) as conn:
        for table in ("batches", "documents", "processing_jobs", "document_files"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    processing = Path(config.get("watch_folder.processing_dir"))
    assert not list(processing.rglob("*.upload"))
    assert not list(processing.glob("web-upload-*.pdf"))
    assert workflow.calls == []


def test_upload_holds_storage_access_until_database_commit(tmp_path, monkeypatch):
    client, config, _ = build_client(tmp_path, monkeypatch)
    original = IngestionAssignmentService.create_batch

    def checked_create(service, **kwargs):
        with pytest.raises(UploadStorageBusy):
            reconcile_upload_files(config)
        assert all(Path(item["file_path"]).exists() for item in kwargs["files"])
        return original(service, **kwargs)

    monkeypatch.setattr(IngestionAssignmentService, "create_batch", checked_create)
    response = client.post(
        "/api/batches/upload", data={"pipeline_version_id": config.pipeline_version_id},
        files=[("files", ("lock-test.pdf", b"%PDF-test", "application/pdf"))],
    )
    assert response.status_code == 200
    assert reconcile_upload_files(config).orphaned_final_removed == 0


def test_upload_returns_retryable_response_during_cleanup(tmp_path, monkeypatch):
    client, config, _ = build_client(tmp_path, monkeypatch)
    with upload_storage_access(config, exclusive=True):
        response = client.post(
            "/api/batches/upload", data={"pipeline_version_id": config.pipeline_version_id},
            files=[("files", ("lock-test.pdf", b"%PDF-test", "application/pdf"))],
        )
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 0
