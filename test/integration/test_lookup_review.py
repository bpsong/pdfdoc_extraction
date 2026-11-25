"""Exercise R3 through published workflow execution, review APIs, and recovery."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import modules.api_router as api_router
from modules.db.connection import json_loads, managed_connect
from modules.db.repositories import (
    AuditRepository, DocumentRepository, ExtractionRepository, LookupKey,
    ProcessingJobRepository, ReviewRepository, TaskRunRepository,
)
from modules.services.lookup_decision_service import LookupDecisionService
from modules.services.processing_lease import JobClaimLost
from modules.services.processing_worker import ProcessingWorker
from modules.services.review_service import ReviewService
from modules.services.startup_migration_service import initialize_database
from modules.services.task_registry_service import ASSIGN_NANOID_TASK
from standard_step.review.review_gate import ReviewGateTask
from standard_step.rules.csv_reference_lookup import CsvReferenceLookupTask
from standard_step.storage.store_metadata_as_json import StoreMetadataAsJson
from test.helpers_business_validation_workflow import offline_invoice_workflows, run_invoice_workflow
from test.helpers_sqlite import TempConfig
from test.integration.test_lookup_pipeline import _add_gate, _definition, _document, _publish


VALUES = {"tax": "00123", "supplier": "acme"}
AMBIGUOUS = "Tax,Name,Code\n00123,Acme,00041\n00123,ACME,00042\n"


@pytest.fixture
def config(tmp_path: Path) -> TempConfig:
    config = TempConfig(tmp_path / "state.sqlite3", {"pipeline_secrets": {"extract": "synthetic-extract-key"}})
    initialize_database(config)
    return config


def _publish_review(
    config: TempConfig, root: Path, *, register: str = AMBIGUOUS,
    schema: dict[str, Any] | None = None, multiple: bool = False, gate_before_lookup: bool = False,
    always_review: bool = False, nanoid: bool = False, repeated_column: bool = False,
) -> dict[str, Any]:
    definition = _definition(root)
    (root / "register.csv").write_text(register, encoding="utf-8")
    if not gate_before_lookup:
        definition["tasks"]["lookup"]["params"].update(on_no_match="review", on_multiple_matches="review")
    if multiple:
        second = deepcopy(definition["tasks"]["lookup"])
        second["params"].update(reference_file="optional.csv", required=False)
        second["params"]["returns"][0]["field"] = "billing_id"
        definition["tasks"]["billing"] = second
        definition["pipeline"].insert(2, "billing")
        (root / "optional.csv").write_text("Tax,Name,Code\n", encoding="utf-8")
    if schema:
        definition["tasks"]["extract"]["params"]["fields"]["approval_code"] = {"type": "str", "alias": "Approval"}
    _add_gate(config, definition, schema=schema, always_review=always_review,
              review_scope="document" if schema else "low_confidence_fields",
              allow_operator_to_edit_high_confidence_fields=False)
    if multiple:
        definition["pipeline"] = ["extract", "lookup", "billing", "gate", "output"]
    if gate_before_lookup:
        definition["pipeline"] = ["extract", "gate", "lookup", "output"]
    if repeated_column:
        definition["tasks"]["lookup"]["params"]["clauses"].append({
            "field": "tax", "column": "Tax", "mode": "numeric",
        })
    if nanoid:
        definition["tasks"]["assign_id"] = {"module": ASSIGN_NANOID_TASK[0], "class": ASSIGN_NANOID_TASK[1]}
        definition["pipeline"].insert(1, "assign_id")
        definition["tasks"]["output"]["params"]["filename"] = "{supplier_id}_{nanoid}"
    return _publish(config, definition)


def _pause(
    config: TempConfig, root: Path, version: dict[str, Any], values: dict[str, Any], *, source: Path | None = None,
) -> tuple[str, str]:
    case = _document(config, root, version, source=source)
    with offline_invoice_workflows(values):
        result = run_invoice_workflow(config, case)
    assert result.get("pipeline_state") == "paused", result.get("error")
    assert not list((root / "exports").glob("*.json"))
    return case["document"]["id"], result["review_item_id"]


def _api(config: TempConfig, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(api_router, "get_dependencies", lambda: (config, None, None, None, None))
    app = FastAPI()
    app.include_router(api_router.build_router())
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    return app


def _action(token: str, record: int | None = 2) -> dict[str, Any]:
    return {"action": "skip" if record is None else "select", "evaluation_token": token,
            "record_number": record, "reason": "Checked synthetic register evidence"}


def test_multiple_lookup_resolution_is_bound_to_claim_and_evidence(
    config: TempConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _publish_review(config, tmp_path, multiple=True, repeated_column=True)
    document_id, review_id = _pause(config, tmp_path, version, VALUES)
    app = _api(config, monkeypatch)
    url = f"/api/review/items/{review_id}"
    with TestClient(app) as client, offline_invoice_workflows():
        app.dependency_overrides.pop(api_router.get_current_user)
        assert client.post(url + "/revalidate", json={}).status_code == 401
        app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
        assert client.post(url + "/claim", json={}).status_code == 200
        detail = client.get(url).json()
        assert "tax" in detail["metadata"]["editable_fields"]
        assert "supplier_id" not in {field["field_key"] for field in detail["fields"]}
        review = detail["lookup_review"]
        by_task = {item["task_key"]: item for item in review["lookups"]}
        assert by_task["lookup"]["match_count"] == 2
        assert by_task["billing"]["can_skip"]
        assert by_task["lookup"]["candidates"][1]["values"] == {"supplier_id": "00042"}
        evidence = by_task["lookup"]["candidates"][1]["match_evidence"]
        assert [(clause["mode"], clause["reference_value"]) for clause in evidence if clause["column"] == "Tax"] == [
            ("case_sensitive", "00123"), ("numeric", "00123"),
        ]
        request = {"expected_revision": detail["review_revision"]}
        edit = {"corrections": {"supplier_id": "MANUAL"}}
        assert client.post(url + "/draft", json={**request, **edit}).json()["detail"]["code"] == "lookup_readonly_field"
        assert client.post(url + "/complete", json=request).status_code == 422
        bad_token = by_task["billing"]["evaluation_token"]
        bad = {"lookup_actions": {"lookup": _action(bad_token)}}
        assert client.post(url + "/complete", json={**request, **bad}).status_code == 409
        bad = {"lookup_actions": {"lookup": _action(by_task["lookup"]["evaluation_token"], 3)}}
        assert client.post(url + "/complete", json={**request, **bad}).status_code == 422
        client.cookies.set("access_token", "synthetic-session")
        client.cookies.set("csrf_token", "synthetic-csrf")
        assert client.post(url + "/revalidate", json=request).status_code == 403
        headers = {"x-csrf-token": "synthetic-csrf"}

        request["lookup_actions"] = {
            "lookup": _action(by_task["lookup"]["evaluation_token"]),
            "billing": _action(bad_token, None),
        }
        preview = client.post(url + "/revalidate", json=request, headers=headers).json()["lookup_review"]
        assert not preview["blocked"]
        assert client.post(url + "/claim", json={}, headers=headers).status_code == 200
        assert client.get(url).json()["review_revision"] == detail["review_revision"]
        request["lookup_preview_token"] = preview["preview_token"]
        app.dependency_overrides[api_router.get_current_user] = lambda: "other"
        assert client.post(url + "/complete", json=request, headers=headers).status_code == 409
        app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
        assert not list((tmp_path / "exports").glob("*.json"))
        # Selection uses recorded candidates even if the register is removed.
        (tmp_path / "register.csv").unlink()
        response = client.post(url + "/complete", json=request, headers=headers)
        assert response.status_code == 200, response.json()
        assert response.json()["resume_triggered"]
        assert client.post(url + "/complete", json=request, headers=headers).status_code == 409
        accepted = client.get(url).json()["lookup_review"]
        assert {item["state"] for item in accepted["lookups"]} == {"matched", "skipped"}

    outputs = list((tmp_path / "exports").glob("*.json"))
    assert len(outputs) == 1
    assert json.loads(outputs[0].read_text(encoding="utf-8")) == {**VALUES, "supplier_id": "00042"}
    with managed_connect(config) as conn:
        decision = LookupDecisionService(conn).current(LookupKey(document_id, version["id"], "lookup"))
        assert decision is not None and decision.selected_record_number == 2
        assert decision.actor == "operator" and decision.reason


def test_lost_claim_invalidates_previously_passing_lookup_preview(
    config: TempConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _publish_review(config, tmp_path, nanoid=True)
    _, review_id = _pause(config, tmp_path, version, VALUES)
    app = _api(config, monkeypatch)
    url = f"/api/review/items/{review_id}"
    with TestClient(app) as client:
        assert client.post(url + "/claim", json={}).status_code == 200
        detail = client.get(url).json()
        token = detail["lookup_review"]["lookups"][0]["evaluation_token"]
        request = {"expected_revision": detail["review_revision"], "lookup_actions": {"lookup": _action(token)}}
        preview = client.post(url + "/revalidate", json=request).json()["lookup_review"]
        assert not preview["blocked"]
        request["lookup_preview_token"] = preview["preview_token"]
        with managed_connect(config) as conn:
            conn.execute("UPDATE review_locks SET expires_at='2000-01-01T00:00:00+00:00' WHERE review_item_id=?", (review_id,))
        app.dependency_overrides[api_router.get_current_user] = lambda: "replacement"
        assert client.post(url + "/claim", json={}).status_code == 200
        assert client.post(url + "/complete", json=request).json()["detail"]["code"] == "stale_review"
        app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
        assert client.post(url + "/complete", json=request).status_code == 409
    assert not list((tmp_path / "exports").glob("*.json"))


def test_corrected_input_and_explicit_file_adoption_require_fresh_preview(
    config: TempConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _publish_review(config, tmp_path, register="Tax,Name,Code\n00123,Acme,00042\n")
    document_id, review_id = _pause(config, tmp_path, version, {**VALUES, "tax": "wrong"})
    url = f"/api/review/items/{review_id}"
    with TestClient(_api(config, monkeypatch)) as client, offline_invoice_workflows():
        client.post(url + "/claim", json={})
        detail = client.get(url).json()
        lookup = detail["lookup_review"]["lookups"][0]
        old_digest = lookup["source_sha256"]
        assert lookup["outcome"] == "no_match"
        request = {"expected_revision": detail["review_revision"], "corrections": {"tax": "00123"}}
        preview = client.post(url + "/revalidate", json=request).json()["lookup_review"]
        assert preview["lookups"][0]["returned_values"] == {"supplier_id": "00042"}

        reference = tmp_path / "register.csv"
        reference.write_text("Tax,Name,Code\n00123,Acme,00055\n", encoding="utf-8")
        response = client.post(url + "/revalidate", json=request)
        assert response.json()["lookup_review"]["lookups"][0]["issue"] == "reference_changed"
        assert client.post(url + "/complete", json=request).status_code == 422
        request["reference_adoptions"] = {"lookup": "Approved replacement register"}
        preview = client.post(url + "/revalidate", json=request).json()["lookup_review"]
        assert preview["lookups"][0]["returned_values"] == {"supplier_id": "00055"}
        request["lookup_preview_token"] = preview["preview_token"]
        reference.write_text("Tax,Name,Code\n00123,Acme,00056\n", encoding="utf-8")
        response = client.post(url + "/complete", json=request)
        assert response.status_code == 409 and response.json()["detail"]["code"] == "stale_lookup_preview"
        assert not list((tmp_path / "exports").glob("*.json"))
        request["lookup_preview_token"] = client.post(url + "/revalidate", json=request).json()["lookup_review"]["preview_token"]
        assert client.post(url + "/complete", json=request).status_code == 200

    with managed_connect(config) as conn:
        service = LookupDecisionService(conn)
        key = LookupKey(document_id, version["id"], "lookup")
        decision = service.current(key)
        assert decision is not None and decision.supersedes_id
        prior = service.get(key, decision.supersedes_id)
        assert prior is not None and prior.evaluation.source_sha256 == old_digest
        assert decision.returned_values() == {"supplier_id": "00056"}
        assert decision.reason == "Approved replacement register"
        extraction = ExtractionRepository(conn).get_latest_result(document_id)
        assert extraction is not None and json_loads(extraction["data_json"])["tax"] == "wrong"
        assert {field["field_key"] for field in ExtractionRepository(conn).get_fields(document_id)} == {"tax", "supplier"}


def test_truncated_candidates_and_changed_inputs_cannot_reuse_old_selection(
    config: TempConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    register = AMBIGUOUS + "00123,Acme,OTHER\n" * 49 + "00999,Acme,00099\n"
    version = _publish_review(config, tmp_path, register=register)
    _, review_id = _pause(config, tmp_path, version, VALUES)
    with TestClient(_api(config, monkeypatch)) as client:
        url = f"/api/review/items/{review_id}"
        client.post(url + "/claim", json={})
        detail = client.get(url).json()
        lookup = detail["lookup_review"]["lookups"][0]
        assert lookup["match_count"] == 51 and lookup["candidates_truncated"]
        assert len(lookup["candidates"]) == 50 and not lookup["can_select"]
        request = {"expected_revision": detail["review_revision"],
                   "lookup_actions": {"lookup": _action(lookup["evaluation_token"])}}
        blocked = client.post(url + "/complete", json=request)
        assert blocked.status_code == 422
        assert blocked.json()["detail"]["lookup_review"]["lookups"][0]["issue"] == "invalid_lookup_resolution"
        request["corrections"] = {"tax": "00999"}
        assert client.post(url + "/complete", json=request).json()["detail"]["code"] == "stale_lookup_selection"
        assert not list((tmp_path / "exports").glob("*.json"))


def test_r4_checks_use_returned_text_and_acceptance_rolls_back_before_restart(
    config: TempConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = {
        "fields": {"tax": {"type": "string"}, "supplier_id": {"type": "string"},
                   "approval_code": {"type": "string"}},
        "business_validation": {"format_version": 1, "rules": [
            {"id": "supplier_approval", "validator": "required_if:v1", "when": "/supplier_id",
             "equals": "00042", "required": ["/approval_code"], "severity": "blocking"},
        ]},
    }
    version = _publish_review(config, tmp_path, schema=schema)
    document_id, review_id = _pause(config, tmp_path, version, VALUES)
    key = LookupKey(document_id, version["id"], "lookup")
    with managed_connect(config) as conn:
        service = ReviewService(conn, config)
        service.claim(review_id, "operator")
        detail = service.get_detail(review_id)
        assert detail is not None
        token = detail["lookup_review"]["lookups"][0]["evaluation_token"]
        request = {"expected_revision": detail["review_revision"], "lookup_actions": {"lookup": _action(token)}}
        preview = service.revalidate(review_id, "operator", {}, **request)
        assert preview["business_validation"]["has_blocking_findings"]
        with pytest.raises(ValueError, match="blocking business"):
            service.complete(review_id, "operator", {}, lookup_preview_token=preview["lookup_review"]["preview_token"],
                             trigger_resume=False, **request)
        values = {"approval_code": "A-01"}
        preview = service.revalidate(review_id, "operator", values, **request)
        assert not preview["business_validation"]["has_blocking_findings"]
        assert preview["business_validation"]["lookup_sources"]["lookup"]["source_sha256"]
        kwargs = {**request, "lookup_preview_token": preview["lookup_review"]["preview_token"], "trigger_resume": False}
        original = AuditRepository.append

        def fail_after_writes(repo: AuditRepository, **data: Any) -> dict[str, Any]:
            if data.get("event_type") == "review_completed":
                raise RuntimeError("Injected acceptance failure")
            return original(repo, **data)

        with monkeypatch.context() as patcher:
            patcher.setattr(AuditRepository, "append", fail_after_writes)
            with pytest.raises(RuntimeError, match="Injected acceptance failure"):
                service.complete(review_id, "operator", values, **kwargs)
        pending = LookupDecisionService(conn).current(key)
        assert pending is not None and pending.state == "pending" and pending.revision == 1
        doc = DocumentRepository(conn).get(document_id)
        assert doc is not None and doc["status"] == "in_review"
        review = ReviewRepository(conn).get(review_id)
        assert review is not None and review["status"] == "in_review"
        assert not list((tmp_path / "exports").glob("*.json"))
        assert service.complete(review_id, "operator", values, **kwargs)["status"] == "completed"
        accepted = service.get_detail(review_id)
        assert accepted is not None
        assert accepted["business_validation"]["lookup_sources"]["lookup"]["decision_id"] != pending.id

    (tmp_path / "register.csv").unlink()
    restarted = TempConfig(tmp_path / "state.sqlite3", config.get_all())
    with TestClient(_api(restarted, monkeypatch)) as client, offline_invoice_workflows():
        url = f"/api/documents/{document_id}/resume"
        assert client.post(url).json() == {"resumed": True}
        assert client.post(url).json() == {"resumed": False}
    outputs = list((tmp_path / "exports").glob("*.json"))
    assert len(outputs) == 1
    assert json.loads(outputs[0].read_text(encoding="utf-8")) == {**VALUES, "approval_code": "A-01", "supplier_id": "00042"}


@pytest.mark.parametrize("after_gate_commit", [False, True])
def test_reclaimed_worker_reuses_lookup_evidence_and_single_gate(
    config: TempConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after_gate_commit: bool,
) -> None:
    version = _publish_review(config, tmp_path, nanoid=True)
    case = _document(config, tmp_path, version)
    doc_id = case["document"]["id"]
    crash_task = ReviewGateTask if after_gate_commit else CsvReferenceLookupTask
    original = crash_task.run

    def interrupted(task: Any, context: dict[str, Any]) -> dict[str, Any]:
        original(task, context)
        raise JobClaimLost("Simulated worker interruption")

    with offline_invoice_workflows(VALUES) as extraction_calls:
        with monkeypatch.context() as patcher:
            patcher.setattr(crash_task, "run", interrupted)
            assert ProcessingWorker(config, worker_id="before-restart").run_once()
        with managed_connect(config) as conn:
            decision = LookupDecisionService(conn).current(LookupKey(doc_id, version["id"], "lookup"))
            assert decision is not None and decision.state == "pending"
            conn.execute("UPDATE processing_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00'")
        (tmp_path / "register.csv").unlink()
        assert ProcessingWorker(config, worker_id="after-restart").run_once()
        assert len(extraction_calls) == 1
    with managed_connect(config) as conn:
        assert conn.execute("SELECT count(*) FROM review_items WHERE document_id=?", (doc_id,)).fetchone()[0] == 1
        review = ReviewRepository(conn).find_latest_for_document(doc_id)
        assert review is not None and review["status"] == "pending"
        gate_run = TaskRunRepository(conn).get(review["created_by_task_run_id"])
        assert gate_run is not None and gate_run["status"] == "paused"
        job = ProcessingJobRepository(conn).get_for_document(doc_id)
        assert job is not None and job["status"] == "completed"
    assert not list((tmp_path / "exports").glob("*.json"))


def test_gate_before_lookup_uses_accepted_input_on_resume(config: TempConfig, tmp_path: Path) -> None:
    version = _publish_review(
        config, tmp_path, register="Tax,Name,Code\n00123,Acme,00042\n",
        gate_before_lookup=True, always_review=True, nanoid=True,
    )
    doc_id, review_id = _pause(config, tmp_path, version, {**VALUES, "tax": "wrong"})
    with managed_connect(config) as conn, offline_invoice_workflows():
        run = TaskRunRepository(conn).latest_completed_at(doc_id, version["id"], 1)
        assert run is not None
        nanoid = json_loads(run["output_json"])["nanoid"]
        service = ReviewService(conn, config)
        service.claim(review_id, "operator")
        detail = service.get_detail(review_id)
        assert detail is not None and "lookup_review" not in detail
        assert service.complete(review_id, "operator", {"tax": "00123"})["resume_triggered"]
    outputs = list((tmp_path / "exports").glob("00042_*.json"))
    assert len(outputs) == 1
    assert json.loads(outputs[0].read_text(encoding="utf-8"))["nanoid"] == nanoid


@pytest.mark.parametrize("crash_stage", ["early_gate", "lookup", "output", "unverified_output"])
def test_worker_recovery_preserves_early_review_and_never_replays_started_export(
    config: TempConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_stage: str,
) -> None:
    version = _publish_review(
        config, tmp_path, register="Tax,Name,Code\n00123,Acme,00042\n",
        gate_before_lookup=True, always_review=crash_stage == "early_gate", nanoid=True,
    )
    case = _document(config, tmp_path, version)
    document_id = case["document"]["id"]
    implementation = {
        "early_gate": ReviewGateTask, "lookup": CsvReferenceLookupTask,
        "output": StoreMetadataAsJson, "unverified_output": StoreMetadataAsJson,
    }[crash_stage]
    original = implementation.run

    def interrupted(task: Any, context: dict[str, Any]) -> dict[str, Any]:
        original(task, context)
        raise JobClaimLost("Simulated worker interruption")

    with offline_invoice_workflows(VALUES) as calls:
        with monkeypatch.context() as patcher:
            patcher.setattr(implementation, "run", interrupted)
            assert ProcessingWorker(config, worker_id="crashed").run_once()
        with managed_connect(config) as conn:
            run = TaskRunRepository(conn).latest_completed_at(document_id, version["id"], 1)
            assert run is not None
            nanoid = json_loads(run["output_json"])["nanoid"]
            conn.execute("UPDATE processing_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00'")
            if crash_stage == "unverified_output":
                artifact = next(
                    item for item in DocumentRepository(conn).list_files(document_id)
                    if item["file_type"] == "export_json"
                )
                Path(artifact["file_path"]).write_text("{}", encoding="utf-8")
        (tmp_path / "register.csv").unlink()
        assert ProcessingWorker(config, worker_id="restarted").run_once()
    assert len(calls) == 1
    with managed_connect(config) as conn:
        job = ProcessingJobRepository(conn).get_for_document(document_id)
        assert job is not None
        assert job["status"] == ("failed" if crash_stage == "unverified_output" else "completed")
        item = ReviewRepository(conn).find_latest_for_document(document_id)
        assert bool(item) == (crash_stage == "early_gate")
        if item:
            assert item["status"] == "pending"
    outputs = list((tmp_path / "exports").glob("*.json"))
    assert len(outputs) == (0 if crash_stage == "early_gate" else 1)
    if crash_stage == "unverified_output":
        assert outputs[0].read_text(encoding="utf-8") == "{}"
    elif outputs:
        assert json.loads(outputs[0].read_text(encoding="utf-8"))["nanoid"] == nanoid


@pytest.mark.parametrize("interrupt_after_registration", [False, True])
def test_worker_recovers_registered_json_export_before_review_gate(
    config: TempConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    interrupt_after_registration: bool,
) -> None:
    definition = _definition(tmp_path)
    (tmp_path / "register.csv").write_text("Tax,Name,Code\n00123,Acme,00042\n", encoding="utf-8")
    _add_gate(config, definition, always_review=True)
    definition["tasks"]["preliminary"] = deepcopy(definition["tasks"]["output"])
    definition["tasks"]["preliminary"]["params"]["filename"] = "preliminary_{supplier_id}"
    definition["pipeline"] = ["extract", "lookup", "preliminary", "gate", "output"]
    version = _publish(config, definition)
    case = _document(config, tmp_path, version)
    document_id = case["document"]["id"]
    original = StoreMetadataAsJson.run

    def interrupted(task: StoreMetadataAsJson, context: dict[str, Any]) -> dict[str, Any]:
        result = original(task, context)
        if context["current_task_key"] == "preliminary":
            if not interrupt_after_registration:
                # Leave the bytes behind and simulate interruption before their receipt.
                with managed_connect(config) as conn:
                    conn.execute(
                        "DELETE FROM document_files WHERE document_id=? AND file_type='export_json'", (document_id,),
                    )
            raise JobClaimLost("Simulated interrupted preliminary JSON export")
        return result

    with offline_invoice_workflows(VALUES) as calls:
        with monkeypatch.context() as patcher:
            patcher.setattr(StoreMetadataAsJson, "run", interrupted)
            assert ProcessingWorker(config, worker_id="crashed").run_once()
        with managed_connect(config) as conn:
            conn.execute("UPDATE processing_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00'")
        assert ProcessingWorker(config, worker_id="restarted").run_once()
    assert len(calls) == 1
    assert len(list((tmp_path / "exports").glob("*.json"))) == 1
    with managed_connect(config) as conn:
        job = ProcessingJobRepository(conn).get_for_document(document_id)
        review = ReviewRepository(conn).find_latest_for_document(document_id)
        assert job is not None and job["status"] == ("completed" if interrupt_after_registration else "failed")
        if not interrupt_after_registration:
            assert "interrupted JSON export cannot be verified" in job["last_error"]
        assert bool(review) == interrupt_after_registration
        if review:
            run = TaskRunRepository(conn).latest_completed_at(document_id, version["id"], 2)
            assert run is not None and json_loads(run["output_json"])["recovered_artifact_id"]
            assert review["status"] == "pending"
            with offline_invoice_workflows():
                service = ReviewService(conn, config)
                service.claim(review["id"], "operator")
                detail = service.get_detail(review["id"])
                assert detail is not None
                revision = detail["review_revision"]
                preview = service.revalidate(review["id"], "operator", {}, expected_revision=revision)
                assert service.complete(
                    review["id"], "operator", {}, expected_revision=revision,
                    lookup_preview_token=preview["lookup_review"]["preview_token"],
                )["resume_triggered"]
    if interrupt_after_registration:
        outputs = sorted(path.name for path in (tmp_path / "exports").glob("*.json"))
        assert outputs == [f"00042_{document_id}.json", "preliminary_00042.json"]


def test_lookup_gate_failure_cannot_continue_to_export(
    config: TempConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = _definition(tmp_path)
    definition["tasks"]["lookup"]["params"]["on_multiple_matches"] = "review"
    (tmp_path / "register.csv").write_text(AMBIGUOUS, encoding="utf-8")
    _add_gate(config, definition)
    definition["tasks"]["gate"]["on_error"] = "continue"
    version = _publish(config, definition)
    case = _document(config, tmp_path, version)

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Injected review service failure")

    monkeypatch.setattr(ReviewService, "create_review_item", unavailable)
    with offline_invoice_workflows(VALUES):
        result = run_invoice_workflow(config, case)
    assert result["error_step"] == "gate"
    assert not list((tmp_path / "exports").glob("*.json"))
    with managed_connect(config) as conn:
        decision = LookupDecisionService(conn).current(LookupKey(case["document"]["id"], version["id"], "lookup"))
        assert decision is not None and decision.state == "pending"
