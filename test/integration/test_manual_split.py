"""Synthetic end-to-end manual decisions, skips, children, and resume tests."""

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from modules.db.connection import connect, json_loads
from modules.db.repositories import DocumentRepository, ReviewRepository, TaskRunRepository
from modules.resume_manager import ResumeManager
from modules.services.batch_service import BatchService
from modules.services.manual_split_service import ManualSplitReviewService, validate_boundaries
from modules.services.review_service import ReviewService, ReviewServiceError
from modules.services.startup_migration_service import initialize_database
from modules.workflow_loader import WorkflowLoader
from standard_step.split.manual_split import ManualSplitTask
from test.helpers_sqlite import TempConfig, seed_pipeline, assign_pipeline
from test.workflow.test_workflow_task_run_tracking import _patch_prefect


@pytest.fixture
def manual_case(tmp_path, monkeypatch):
    config = TempConfig(tmp_path / "app.sqlite3", {"pipeline": ["manual", "next"], "tasks": {
        "manual": {"module": "standard_step.split.manual_split", "class": "ManualSplitTask", "params": {"split_dir": str(tmp_path / "split")}, "on_error": "stop"},
        "next": {"module": "tests", "class": "NextTask", "params": {}, "on_error": "stop"},
    }})
    initialize_database(config)
    version = seed_pipeline(config)
    downstream = []

    class NextTask:
        def __init__(self, **kwargs):
            pass

        def on_start(self, context):
            pass

        def run(self, context):
            downstream.append(dict(context))
            return context

    class CleanupTask(NextTask):
        def run(self, context):
            return context

    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    monkeypatch.setattr(WorkflowLoader, "_import_task_class", lambda self, module, cls: ManualSplitTask if cls == "ManualSplitTask" else NextTask)

    def start(pages: int):
        pdf = tmp_path / f"source-{pages}.pdf"
        writer = PdfWriter()
        for index in range(pages):
            writer.add_blank_page(width=200 + index, height=300)
        with pdf.open("wb") as stream:
            writer.write(stream)
        with connect(config) as conn:
            created = BatchService(conn).create_ingestion_batch(source="test", file_path=str(pdf), original_filename=pdf.name)
        document = created["document"]
        assign_pipeline(config, document["id"], version)
        from modules.services.pipeline_definition_service import PipelineDefinitionService
        with connect(config) as conn:
            executable = PipelineDefinitionService(conn, config).load_for_document(document["id"])
        loader = WorkflowLoader(config, definition=executable.definition, pipeline_version_id=executable.version_id, pipeline_template_id=executable.template_id)
        result = loader.load_workflow()({"id": document["id"], "document_id": document["id"], "batch_id": document["batch_id"], "file_path": str(pdf), "original_filename": pdf.name, "pipeline_version_id": version["id"], "data": {"nanoid": "keep-me"}, "metadata": {}})
        return document, result

    return config, start, downstream


def approve(config, review_id: str, boundaries: list[int]):
    with connect(config) as conn:
        ReviewService(conn, config).claim(review_id, "admin")
        result = ManualSplitReviewService(conn, config).save(review_id, "admin", {"boundaries": boundaries, "action": "split" if boundaries else "skip", "expected_revision": 1}, complete=True)
        conn.commit()
    return result


def test_one_page_skips_without_review_children_or_fanout(manual_case):
    config, start, downstream = manual_case
    document, result = start(1)
    assert result["data"]["split_result"]["reason"] == "single_page"
    assert result.get("pipeline_state") != "fan_out"
    assert [item["document_id"] for item in downstream] == [document["id"]]
    with connect(config) as conn:
        assert ReviewRepository(conn).list_queue() == []
        assert DocumentRepository(conn).list_children(document["id"]) == []
        assert conn.execute("SELECT COUNT(*) FROM document_files WHERE file_type='split_pdf'").fetchone()[0] == 0
        assert [run["status"] for run in TaskRunRepository(conn).list_by_document(document["id"])] == ["completed", "completed", "completed"]


def test_operator_no_split_resumes_original_without_children(manual_case):
    config, start, downstream = manual_case
    document, result = start(4)
    assert not downstream
    assert result["pipeline_state"] == "paused"
    approve(config, result["review_item_id"], [])
    assert ResumeManager(config).resume_document(document["id"], "admin")
    assert len(downstream) == 1
    assert downstream[0]["document_id"] == document["id"]
    assert downstream[0]["file_path"] == document["file_path"]
    assert downstream[0]["data"]["nanoid"] == "keep-me"
    assert downstream[0]["data"]["split_result"]["reason"] == "operator_no_split"
    with connect(config) as conn:
        assert DocumentRepository(conn).list_children(document["id"]) == []
        assert ReviewRepository(conn).get(result["review_item_id"])["status"] == "completed"
    assert not ResumeManager(config).resume_document(document["id"], "admin")


def test_confirmed_split_materializes_correct_children_and_dispatches_once(manual_case):
    config, start, downstream = manual_case
    document, result = start(4)
    approve(config, result["review_item_id"], [1, 3])
    assert ResumeManager(config).resume_document(document["id"], "admin")
    with connect(config) as conn:
        children = sorted(DocumentRepository(conn).list_children(document["id"]), key=lambda child: child["page_start"])
        assert [(c["page_start"], c["page_end"]) for c in children] == [(1, 1), (2, 3), (4, 4)]
        assert [len(PdfReader(c["file_path"]).pages) for c in children] == [1, 2, 1]
        assert [float(PdfReader(c["file_path"]).pages[0].mediabox.width) for c in children] == [200, 201, 203]
        assert all(c["pipeline_version_id"] == downstream[0]["pipeline_version_id"] for c in children)
        assert all(c["split_confidence"] is None for c in children)
        assert conn.execute("SELECT COUNT(*) FROM document_files WHERE file_type='split_pdf'").fetchone()[0] == 3
        assert DocumentRepository(conn).get(document["id"])["status"] == "completed"
        assert conn.execute("SELECT phase FROM manual_split_decisions").fetchone()[0] == "applied"
    assert {c["document_id"] for c in downstream} == {c["id"] for c in children}
    assert all(c["data"]["nanoid"] == "keep-me" for c in downstream)
    assert not ResumeManager(config).resume_document(document["id"], "admin")
    assert len(downstream) == 3


def test_draft_revision_lock_and_wrong_endpoint_guards(manual_case):
    config, start, _ = manual_case
    _, result = start(4)
    review_id = result["review_item_id"]
    with connect(config) as conn:
        service = ManualSplitReviewService(conn, config)
        with pytest.raises(ReviewServiceError, match="claimed"):
            service.save(review_id, "admin", {"boundaries": [2], "expected_revision": 1})
        ReviewService(conn, config).claim(review_id, "admin")
        assert service.save(review_id, "admin", {"boundaries": [2], "expected_revision": 1})["manual_split"]["revision"] == 2
        with pytest.raises(ReviewServiceError, match="changed"):
            service.save(review_id, "admin", {"boundaries": [1], "expected_revision": 1})
        with pytest.raises(ReviewServiceError, match="another operator"):
            service.save(review_id, "operator", {"boundaries": [2], "expected_revision": 2})
        with pytest.raises(ReviewServiceError, match="manual split decision endpoint"):
            ReviewService(conn, config).complete(review_id, "admin", {})
        detail = ReviewService(conn, config).get_detail(review_id)
        assert detail["schema"] is None
        assert detail["fields"] == []
        assert detail["manual_split"]["boundaries"] == [2]
        assert ReviewService(conn, config).list_items()[0]["lowest_confidence"] is None


def test_changed_source_rejected_without_children(manual_case):
    config, start, _ = manual_case
    document, result = start(4)
    with Path(document["file_path"]).open("ab") as stream:
        stream.write(b"\n%source changed\n")
    with pytest.raises(ReviewServiceError, match="changed"):
        approve(config, result["review_item_id"], [2])
    with connect(config) as conn:
        assert DocumentRepository(conn).list_children(document["id"]) == []


def test_accepted_decision_recovers_failed_launch_without_reapproval(manual_case, monkeypatch):
    from modules.services.manual_split_service import recover_manual_split
    config, start, downstream = manual_case
    document, result = start(4)
    approve(config, result["review_item_id"], [2])
    original = WorkflowLoader.load_workflow
    monkeypatch.setattr(WorkflowLoader, "load_workflow", lambda *args, **kwargs: None)
    assert not ResumeManager(config).resume_document(document["id"], "admin")
    with connect(config) as conn:
        assert DocumentRepository(conn).get(document["id"])["status"] == "review_completed"
    monkeypatch.setattr(WorkflowLoader, "load_workflow", original)
    assert recover_manual_split(config, result["review_item_id"], "admin")["resumed"]
    assert len(downstream) == 2


def test_recovery_dispatches_only_unstarted_children(manual_case, monkeypatch):
    from modules.services.manual_split_service import recover_manual_split
    from modules.workflow_manager import WorkflowManager
    config, start, downstream = manual_case
    document, result = start(4)
    approve(config, result["review_item_id"], [1, 2, 3])
    original = WorkflowManager._trigger_child_workflows
    monkeypatch.setattr(WorkflowManager, "_trigger_child_workflows", lambda *args: None)
    assert ResumeManager(config).resume_document(document["id"], "admin")
    assert not downstream
    monkeypatch.setattr(WorkflowManager, "_trigger_child_workflows", original)
    assert recover_manual_split(config, result["review_item_id"], "admin")["resumed"]
    assert len(downstream) == 4
    assert not recover_manual_split(config, result["review_item_id"], "admin")["resumed"]
    assert len(downstream) == 4


def test_final_decision_is_idempotent_and_immutable(manual_case):
    config, start, _ = manual_case
    _, result = start(4)
    approve(config, result["review_item_id"], [2])
    with connect(config) as conn:
        service = ManualSplitReviewService(conn, config)
        assert service.save(result["review_item_id"], "admin", {"action": "split", "boundaries": [2], "expected_revision": 1}, complete=True)["status"] == "completed"
        with pytest.raises(ReviewServiceError, match="already final"):
            service.save(result["review_item_id"], "admin", {"action": "split", "boundaries": [1], "expected_revision": 1}, complete=True)


def test_recovery_cannot_reset_a_claimed_continuation(manual_case):
    from modules.services.manual_split_service import recover_manual_split

    config, start, downstream = manual_case
    document, result = start(2)
    approve(config, result["review_item_id"], [])
    with connect(config) as conn:
        assert DocumentRepository(conn).claim_review_resume(document["id"])
    with pytest.raises(ReviewServiceError, match="already been claimed"):
        recover_manual_split(config, result["review_item_id"], "admin")
    with connect(config) as conn:
        assert DocumentRepository(conn).get(document["id"])["status"] == "resuming"
    assert downstream == []


def test_successful_recovery_does_not_inherit_the_failed_split_attempt(manual_case, monkeypatch):
    from modules.services import manual_split_service
    from modules.db.repositories import ExtractionRepository

    config, start, downstream = manual_case
    document, result = start(2)
    approve(config, result["review_item_id"], [1])
    original = manual_split_service.create_split_pdf

    def unavailable_disk(*args):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(manual_split_service, "create_split_pdf", unavailable_disk)
    assert ResumeManager(config).resume_document(document["id"], "admin")
    with connect(config) as conn:
        assert DocumentRepository(conn).get(document["id"])["status"] == "failed"
    monkeypatch.setattr(manual_split_service, "create_split_pdf", original)
    assert manual_split_service.recover_manual_split(config, result["review_item_id"], "admin")["resumed"]
    assert len(downstream) == 2
    assert all(not child.get("continued_failures") for child in downstream)
    with connect(config) as conn:
        source = DocumentRepository(conn).get(document["id"])
        assert source["status"] == "completed"
        # Subsequent context reconstruction must also recognize the successful
        # retry while retaining the failed attempt in the audit history.
        context = ResumeManager(config)._build_resume_context(source, ExtractionRepository(conn), TaskRunRepository(conn))
        assert not context.get("continued_failures")
        assert any(run["status"] == "failed" for run in TaskRunRepository(conn).list_by_document(document["id"]))


def test_unavailable_child_loader_leaves_children_retryable(manual_case, monkeypatch):
    from modules.services.manual_split_service import recover_manual_split

    config, start, downstream = manual_case
    document, result = start(2)
    approve(config, result["review_item_id"], [1])
    original = WorkflowLoader.load_workflow

    def unavailable_children(self, start_task_index=0):
        return None if start_task_index == 1 else original(self, start_task_index=start_task_index)

    monkeypatch.setattr(WorkflowLoader, "load_workflow", unavailable_children)
    assert ResumeManager(config).resume_document(document["id"], "admin")
    with connect(config) as conn:
        children = DocumentRepository(conn).list_children(document["id"])
        assert len(children) == 2
        assert all(child["status"] == "queued" for child in children)
    assert downstream == []
    monkeypatch.setattr(WorkflowLoader, "load_workflow", original)
    assert recover_manual_split(config, result["review_item_id"], "admin")["resumed"]
    assert len(downstream) == 2


@pytest.mark.parametrize("task_key,module_name,class_name", [
    ("next", "tests", "NextTask"),
    ("cleanup_task", "standard_step.housekeeping.cleanup_task", "CleanupTask"),
])
def test_recovery_still_rejects_failed_downstream_or_cleanup(manual_case, task_key, module_name, class_name):
    from modules.services.manual_split_service import recover_manual_split

    config, start, downstream = manual_case
    document, result = start(2)
    approve(config, result["review_item_id"], [])
    with connect(config) as conn:
        runs = TaskRunRepository(conn)
        source = DocumentRepository(conn).get(document["id"])
        run = runs.create_started(
            batch_id=document["batch_id"], document_id=document["id"],
            task_key=task_key, task_index=1, module_name=module_name,
            class_name=class_name, pipeline_version_id=source["pipeline_version_id"],
        )
        runs.mark_failed(run["id"], "Synthetic downstream failure")
    with pytest.raises(ReviewServiceError, match="Downstream work"):
        recover_manual_split(config, result["review_item_id"], "admin")
    assert not ResumeManager(config).resume_document(document["id"], "admin")
    assert downstream == []


def test_recovered_dispatch_records_downstream_preflight_failure(manual_case, monkeypatch):
    from modules.exceptions import TaskError
    from modules.services.manual_split_service import recover_manual_split
    from modules.workflow_manager import WorkflowManager

    config, start, downstream = manual_case
    document, result = start(2)
    approve(config, result["review_item_id"], [1])
    original = WorkflowManager._trigger_child_workflows
    monkeypatch.setattr(WorkflowManager, "_trigger_child_workflows", lambda *args: None)
    assert ResumeManager(config).resume_document(document["id"], "admin")
    monkeypatch.setattr(WorkflowManager, "_trigger_child_workflows", original)
    monkeypatch.setattr(WorkflowManager, "_task_at_index", lambda *args, **kwargs: (
        "next", {"module": "standard_step.extraction.llamacloud_extract",
                 "class": "LlamaCloudExtractTask", "params": {}},
    ))
    monkeypatch.setattr(WorkflowManager, "_is_llamacloud_extract_task", lambda *args: True)

    def unavailable_provider(**kwargs):
        raise TaskError("Synthetic preflight failure")

    monkeypatch.setattr("modules.workflow_manager.preflight_extract_v2_access", unavailable_provider)
    recover_manual_split(config, result["review_item_id"], "admin")
    with connect(config) as conn:
        documents = DocumentRepository(conn)
        assert documents.get(document["id"])["status"] == "failed"
        assert all(child["status"] == "failed" for child in documents.list_children(document["id"]))
        failures = [run for run in TaskRunRepository(conn).list_by_document(document["id"]) if run["status"] == "failed"]
        assert len(failures) == 1
        assert failures[0]["error"] == "Synthetic preflight failure"
    assert downstream == []


def test_manual_api_draft_and_completion(manual_case, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import modules.api_router as router
    config, start, _ = manual_case
    document, result = start(4)
    review_id = result["review_item_id"]
    with connect(config) as conn:
        ReviewService(conn, config).claim(review_id, "admin")
    monkeypatch.setattr(router, "get_dependencies", lambda: (config, None, None, None, None))
    monkeypatch.setattr(ResumeManager, "resume_document", lambda *args, **kwargs: True)
    app = FastAPI()
    app.dependency_overrides[router.get_current_user] = lambda: "admin"
    app.include_router(router.build_router())
    with TestClient(app) as client:
        saved = client.post(f"/api/review/items/{review_id}/split/draft", json={"boundaries": [2], "expected_revision": 1})
        assert saved.status_code == 200
        assert saved.json()["manual_split"]["revision"] == 2
        final = client.post(f"/api/review/items/{review_id}/split/complete", json={"boundaries": [2], "action": "split", "expected_revision": 2})
        assert final.status_code == 202
        assert final.json()["resume_scheduled"]
        assert final.json()["document_id"] == document["id"]


def test_split_acknowledgment_precedes_slow_child_workflow(manual_case, monkeypatch):
    """Observe the ASGI wire response while a real child flow is still blocked."""
    import asyncio
    import json
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from fastapi import FastAPI
    import modules.api_router as router

    config, start, _ = manual_case
    document, result = start(4)
    review_id = result["review_item_id"]
    with connect(config) as conn:
        ReviewService(conn, config).claim(review_id, "operator")
    entered, release, response_sent = Event(), Event(), Event()
    original_import = WorkflowLoader._import_task_class

    class SlowTask:
        def __init__(self, **kwargs):
            pass

        def on_start(self, context):
            pass

        def run(self, context):
            entered.set()
            assert release.wait(15), "Test did not release the child workflow"
            return context

    monkeypatch.setattr(WorkflowLoader, "_import_task_class", lambda self, module, cls:
                        SlowTask if cls == "NextTask" else original_import(self, module, cls))
    monkeypatch.setattr(router, "get_dependencies", lambda: (config, None, None, None, None))
    app = FastAPI()
    app.dependency_overrides[router.get_current_user] = lambda: "operator"
    app.include_router(router.build_router())
    messages = []
    payload = json.dumps({"action": "split", "boundaries": [2], "expected_revision": 1}).encode()

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body"):
            response_sent.set()

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "query_string": b"",
             "path": f"/api/review/items/{review_id}/split/complete",
             "headers": [(b"content-type", b"application/json")],
             "server": ("testserver", 80), "client": ("testclient", 123)}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, app(scope, receive, send))
        try:
            assert entered.wait(10)
            assert response_sent.is_set(), "HTTP response waited for child extraction"
            assert not future.done()
            assert messages[0]["status"] == 202
            response = json.loads(next(m["body"] for m in messages if m["type"] == "http.response.body"))
            assert response["status"] == "completed" and response["resume_scheduled"]
            with connect(config) as conn:
                assert ReviewRepository(conn).get(review_id)["status"] == "completed"
                assert len(DocumentRepository(conn).list_children(document["id"])) == 2
        finally:
            release.set()
            future.result(timeout=10)
    with connect(config) as conn:
        assert DocumentRepository(conn).get(document["id"])["status"] == "completed"


def test_version7_migration_preserves_reviews_as_extraction(manual_case):
    config, start, _ = manual_case
    _, result = start(4)
    with connect(config) as conn:
        conn.execute("DROP TABLE manual_split_decisions")
        conn.execute("ALTER TABLE review_items DROP COLUMN review_kind")
        conn.execute("DELETE FROM schema_migrations WHERE version=8")
        conn.execute("INSERT INTO schema_migrations(version,applied_at) VALUES (7,'synthetic')")
    initialize_database(config)
    initialize_database(config)
    with connect(config) as conn:
        assert ReviewRepository(conn).get(result["review_item_id"])["review_kind"] == "extraction"
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 8
        assert conn.execute("SELECT COUNT(*) FROM manual_split_decisions").fetchone()[0] == 0


@pytest.mark.parametrize("invalid", [[True], [0], [4], [1.5], [2, 2], [3, 1], "2", None])
def test_invalid_boundaries_rejected(invalid):
    with pytest.raises(ReviewServiceError):
        validate_boundaries(invalid, 4)


@pytest.mark.parametrize("action", [[], {}, True, None, "delete"])
def test_malformed_action_is_a_review_conflict(manual_case, action):
    config, start, _ = manual_case
    _, result = start(4)
    with connect(config) as conn:
        ReviewService(conn, config).claim(result["review_item_id"], "admin")
        with pytest.raises(ReviewServiceError, match="Choose split"):
            ManualSplitReviewService(conn, config).save(result["review_item_id"], "admin", {"boundaries": [], "action": action, "expected_revision": 1}, complete=True)
