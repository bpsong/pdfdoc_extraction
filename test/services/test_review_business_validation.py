"""Pinned business-rule enforcement, snapshots, and atomic review acceptance."""

from contextlib import closing
from typing import Any

import pytest

from test.helpers_assertions import require_present

from modules.db.connection import connect, json_loads
from modules.db.repositories import DocumentRepository, ExtractionRepository, ReviewRepository
from modules.exceptions import TaskError
from modules.services.review_service import ReviewBusinessError, ReviewService, ReviewServiceError
from modules.services.startup_migration_service import initialize_database
from test.helpers_business_validation import invoice_review_schema, seed_business_review
from test.helpers_sqlite import TempConfig


@pytest.fixture
def review(tmp_path):
    config = TempConfig(tmp_path / "state.sqlite3")
    initialize_database(config)
    seeded = seed_business_review(config, tmp_path)
    seeded["task"].run(seeded["context"])
    with closing(connect(config)) as conn:
        service = ReviewService(conn, config)
        review_id = seeded["context"]["review_item_id"]
        service.claim(review_id, "operator")
        yield {**seeded, "config": config, "conn": conn, "service": service, "id": review_id}


def detail(review: dict[str, Any]) -> dict[str, Any]:
    return require_present(review["service"].get_detail(review["id"]))


def good_values() -> dict[str, Any]:
    return {"items": [{"quantity": 3, "unit_price": 10, "line_total": 30}], "subtotal": 30}


def database_state(conn) -> dict[str, list[tuple]]:
    return {name: [tuple(row) for row in conn.execute(f"SELECT * FROM {name} ORDER BY rowid")]
            for name in ("review_items", "review_locks", "extracted_fields", "task_runs", "documents", "audit_events")}


def test_gate_pins_report_and_keeps_both_independent_findings(review):
    payload = detail(review)
    report = payload["business_validation"]
    assert report["schema_format_version"] == 2
    assert report["schema_version_id"] == review["version"]["id"]
    assert report["extraction_result_id"] == review["extraction"]["id"]
    assert review["source"]["id"] in report["source_artifact_ids"]
    assert [check["status"] for check in report["checks"]] == ["failed", "failed"]
    assert report["has_blocking_findings"]
    assert payload["metadata"]["highlight_fields"] == ["items", "subtotal"]
    assert len([reason for reason in payload["metadata"]["reasons"]
                if reason["reason"] == "business_validation"]) == 2
    doc = require_present(DocumentRepository(review["conn"]).get(review["context"]["document_id"]))
    assert json_loads(doc["metadata_json"])["business_validation"]["gate"]["task_run_id"] == review["run"]["id"]
    # Re-running the gate retains one open item for this task.
    review["task"].run(review["context"])
    assert review["conn"].execute("SELECT count(*) FROM review_items").fetchone()[0] == 1


def test_unsaved_revalidate_has_no_writes_or_lock_extension(review):
    before = database_state(review["conn"])
    payload = detail(review)
    result = review["service"].revalidate(review["id"], "operator", good_values(),
        expected_revision=payload["review_revision"], request_revision="local-edit-7")
    assert not result["business_validation"]["has_blocking_findings"]
    assert all(check["status"] == "passed" for check in result["business_validation"]["checks"])
    assert result["request_revision"] == "local-edit-7"
    assert result["business_validation"]["review_revision"] == payload["review_revision"]
    assert result["business_validation"]["values_revision"] != payload["business_validation"]["values_revision"]
    assert database_state(review["conn"]) == before


def test_draft_report_on_load_and_submitted_completion_is_rechecked(review):
    original = detail(review)
    saved = review["service"].save_draft(review["id"], "operator", good_values(),
                                        expected_revision=original["review_revision"])
    assert not saved["business_validation"]["has_blocking_findings"]
    assert saved["review_revision"] != original["review_revision"]
    # A passing draft is not evidence that a different final request passes.
    with pytest.raises(ReviewBusinessError) as blocked:
        review["service"].complete(review["id"], "operator", {}, trigger_resume=False,
                                   expected_revision=saved["review_revision"])
    assert blocked.value.detail["code"] == "business_validation_blocked"
    assert detail(review)["metadata"]["draft"]["corrections"] == good_values()
    review["service"].complete(review["id"], "operator", good_values(), trigger_resume=False,
                               expected_revision=saved["review_revision"])
    accepted = detail(review)
    assert accepted["review_item"]["status"] == "completed"
    assert "draft" not in accepted["metadata"]
    assert accepted["business_validation"] == accepted["metadata"]["business_validation"]["accepted"]
    assert accepted["business_validation"]["values_revision"] == saved["business_validation"]["values_revision"]
    output = json_loads(review["conn"].execute("SELECT output_json FROM task_runs WHERE id=?",
                       (review["run"]["id"],)).fetchone()[0])
    assert output["business_validation"] == accepted["business_validation"]
    event = json_loads(review["conn"].execute("SELECT event_json FROM audit_events WHERE event_type='review_completed'").fetchone()[0])
    assert set(event) == {"field_keys", "business_validation"}
    assert "checks" not in event["business_validation"]
    assert "diff" not in event


@pytest.mark.parametrize("method", ["save_draft", "revalidate", "complete"])
def test_revision_required_and_stale_for_all_write_or_validation_requests(review, method):
    operation = getattr(review["service"], method)
    kwargs = {"trigger_resume": False} if method == "complete" else {}
    for token, code in ((None, "review_revision_required"), ("stale", "stale_review")):
        with pytest.raises(ReviewBusinessError) as error:
            operation(review["id"], "operator", good_values(), expected_revision=token, **kwargs)
        assert error.value.detail["code"] == code
    stale = detail(review)["review_revision"]
    review["service"].save_draft(review["id"], "operator", good_values(), expected_revision=stale)
    with pytest.raises(ReviewBusinessError, match="changed"):
        operation(review["id"], "operator", good_values(), expected_revision=stale, **kwargs)


@pytest.mark.parametrize("change", ["values", "extraction", "owner", "expired"])
def test_completion_rechecks_source_and_owner_after_calculation(review, monkeypatch, change):
    service = review["service"]
    token = detail(review)["review_revision"]
    original = service._business_report
    def changed(snapshot, values):
        report = original(snapshot, values)
        with closing(connect(review["config"])) as other:
            if change == "values":
                ExtractionRepository(other).apply_corrections(review["context"]["document_id"], {"subtotal": 31})
            elif change == "extraction":
                ExtractionRepository(other).save_result(document_id=review["context"]["document_id"], provider="retry", data={})
            elif change == "owner":
                other.execute("UPDATE review_locks SET locked_by='other' WHERE review_item_id=?", (review["id"],))
            else:
                other.execute("UPDATE review_locks SET expires_at='2000-01-01T00:00:00+00:00' WHERE review_item_id=?", (review["id"],))
            other.commit()
        return report
    monkeypatch.setattr(service, "_business_report", changed)
    with pytest.raises(ReviewServiceError):
        service.complete(review["id"], "operator", good_values(), expected_revision=token, trigger_resume=False)
    assert require_present(ReviewRepository(review["conn"]).get(review["id"]))["status"] == "in_review"
    assert review["conn"].execute("SELECT count(*) FROM audit_events WHERE event_type='review_completed'").fetchone()[0] == 0
    fields = ExtractionRepository(review["conn"]).get_fields(review["context"]["document_id"])
    assert json_loads(next(f for f in fields if f["field_key"] == "items")["final_value_json"])[0]["line_total"] == 300


@pytest.mark.parametrize("failure", ["review", "task", "state", "audit"])
@pytest.mark.parametrize("nested", [False, True])
def test_acceptance_rolls_back_every_write_and_preserves_outer_scope(review, monkeypatch, failure, nested):
    service, conn = review["service"], review["conn"]
    # Missing persisted field must be inserted on acceptance, and rolled back on failure.
    conn.execute("DELETE FROM extracted_fields WHERE field_key='subtotal'")
    conn.commit()
    if nested:
        conn.execute("UPDATE batches SET source='outer-scope'")
    before = database_state(conn)
    token = detail(review)["review_revision"]
    target, method = {"review": (service.reviews, "complete"), "task": (service.task_runs, "mark_completed"),
                      "state": (service.state, "transition_document"), "audit": (service.audit, "append")}[failure]
    original = getattr(target, method)
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic acceptance failure")
    monkeypatch.setattr(target, method, fail)
    with pytest.raises(RuntimeError, match="synthetic acceptance"):
        service.complete(review["id"], "operator", good_values(), expected_revision=token, trigger_resume=False)
    assert database_state(conn) == before
    assert conn.in_transaction == nested
    if nested:
        assert conn.execute("SELECT source FROM batches").fetchone()[0] == "outer-scope"
        conn.rollback()


def test_accepts_warning_and_missing_field_before_resume_sees_committed_report(review, monkeypatch):
    from modules.resume_manager import ResumeManager
    conn = review["conn"]
    conn.execute("DELETE FROM extracted_fields WHERE field_key='subtotal'")
    conn.commit()
    calls = []
    def resume(_self, document_id, *, user):
        with closing(connect(review["config"])) as other:
            fields = {f["field_key"]: json_loads(f["final_value_json"]) for f in ExtractionRepository(other).get_fields(document_id)}
            assert fields["subtotal"] == 300
            assert require_present(ReviewRepository(other).get(review["id"]))["status"] == "completed"
            accepted = json_loads(require_present(ReviewRepository(other).get(review["id"]))["metadata_json"])["business_validation"]["accepted"]
            assert [c["status"] for c in accepted["checks"]] == ["failed", "passed"]
        calls.append((document_id, user))
        return True
    monkeypatch.setattr(ResumeManager, "resume_document", resume)
    result = review["service"].complete(review["id"], "operator", {"subtotal": 300},
        expected_revision=detail(review)["review_revision"])
    assert result["resume_triggered"] and len(calls) == 1
    with pytest.raises(ReviewServiceError, match="no longer"):
        review["service"].complete(review["id"], "operator", {}, expected_revision="old")
    assert len(calls) == 1


@pytest.mark.parametrize("corrections", [None, [], {"subtotal": float("nan")}, {"unknown": 1}])
def test_invalid_corrections_never_change_state(review, corrections):
    before = database_state(review["conn"])
    with pytest.raises(ReviewServiceError):
        review["service"].revalidate(review["id"], "operator", corrections,
                                    expected_revision=detail(review)["review_revision"])
    assert database_state(review["conn"]) == before


def test_readonly_and_wrong_owner_are_enforced(review):
    token = detail(review)["review_revision"]
    with pytest.raises(ReviewServiceError, match="another operator"):
        review["service"].revalidate(review["id"], "other", good_values(), expected_revision=token)
    metadata = detail(review)["metadata"]
    metadata["editable_fields"] = ["items"]
    ReviewRepository(review["conn"]).update_metadata(review["id"], metadata)
    with pytest.raises(ReviewServiceError, match="not editable"):
        review["service"].revalidate(review["id"], "operator", {"subtotal": 300},
                                    expected_revision=detail(review)["review_revision"])


def test_evaluator_failure_and_missing_values_block_without_leaking_error(review, monkeypatch):
    import modules.services.review_business_validation as runtime
    before = database_state(review["conn"])
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("secret document value")
    monkeypatch.setattr(runtime, "evaluate_business_rules", unavailable)
    report = detail(review)["business_validation"]
    assert report["evaluation_status"] == "error"
    assert "secret document" not in str(report)
    with pytest.raises(ReviewBusinessError) as blocked:
        review["service"].complete(review["id"], "operator", good_values(), trigger_resume=False,
            expected_revision=detail(review)["review_revision"])
    assert blocked.value.detail["code"] == "business_validation_blocked"
    assert database_state(review["conn"]) == before


@pytest.mark.parametrize("require_review,severity,paused", [(False, "warning", False), (True, "warning", True), (False, "blocking", True)])
def test_gate_policy_and_persisted_values_cannot_be_bypassed(tmp_path, require_review, severity, paused):
    config = TempConfig(tmp_path / "state.sqlite3")
    initialize_database(config)
    schema = invoice_review_schema()
    schema["business_validation"]["rules"] = [schema["business_validation"]["rules"][0]]
    schema["business_validation"]["rules"][0].update(require_review=require_review, severity=severity)
    seeded = seed_business_review(config, tmp_path, schema=schema)
    # Context supplied by another task must not override authoritative extracted values.
    seeded["context"]["data"] = good_values()
    result = seeded["task"].run(seeded["context"])
    assert result["review_required"] is paused
    assert result["business_validation"]["checks"][0]["status"] == "failed"
    with closing(connect(config)) as conn:
        assert json_loads(require_present(DocumentRepository(conn).get(seeded["context"]["document_id"]))["metadata_json"])["business_validation"]["gate"]


def test_legacy_form_with_rules_requires_explicit_capability_upgrade(review, monkeypatch):
    from modules.services.review_schema_version_service import ReviewSchemaVersionService
    original = ReviewSchemaVersionService.load_version
    def legacy(self, version_id):
        return {**original(self, version_id), "format_version": 1}
    monkeypatch.setattr(ReviewSchemaVersionService, "load_version", legacy)
    with pytest.raises(ReviewBusinessError, match="incompatible"):
        detail(review)
    with pytest.raises(TaskError, match="incompatible"):
        review["task"].run(review["context"])


def test_invalid_pinned_schema_is_a_structured_failure(review, monkeypatch):
    from modules.services.review_schema_version_service import ReviewSchemaVersionService

    original = ReviewSchemaVersionService.load_version

    def invalid(self, version_id):
        return {**original(self, version_id), 'schema': None}

    monkeypatch.setattr(ReviewSchemaVersionService, 'load_version', invalid)
    before = database_state(review['conn'])
    with pytest.raises(ReviewBusinessError) as error:
        detail(review)
    assert error.value.status_code == 422
    assert error.value.detail['code'] == 'review_schema_unavailable'
    assert database_state(review['conn']) == before


def test_manual_split_is_rejected_by_business_endpoint(review):
    review["conn"].execute("UPDATE review_items SET review_kind='manual_split' WHERE id=?", (review["id"],))
    review["conn"].commit()
    with pytest.raises(ReviewServiceError, match="manual split"):
        review["service"].revalidate(review["id"], "operator", {}, expected_revision="unused")


@pytest.mark.parametrize("values,status", [
    ({"items": [], "subtotal": 0}, "not_evaluated"),
    ({"items": [{"quantity": 1, "unit_price": 5, "line_total": None}], "subtotal": 5}, "not_evaluated"),
    ({"items": "invalid", "subtotal": 0}, "not_evaluated"),
])
def test_inconclusive_or_schema_invalid_submissions_cannot_complete(review, values, status):
    before = database_state(review["conn"])
    with pytest.raises(ReviewBusinessError) as error:
        review["service"].complete(review["id"], "operator", values, trigger_resume=False,
            expected_revision=detail(review)["review_revision"])
    assert error.value.status_code == 422
    assert error.value.detail["business_validation"]["checks"][1]["status"] == status
    assert database_state(review["conn"]) == before


def test_gate_preserves_confidence_schema_and_legacy_reasons(review):
    conn = review["conn"]
    conn.execute("UPDATE extracted_fields SET confidence=.1 WHERE field_key='items'")
    ReviewRepository(conn).complete(review["id"], "operator")
    conn.commit()
    review["task"].field_threshold_overrides = {"items": .8}
    review["context"]["review_flags"] = {"reference_missing": {"field_keys": ["subtotal"]}}
    review["context"]["data"] = {"items": "bad"}
    review["task"].run(review["context"])
    item = require_present(ReviewRepository(conn).get(review["context"]["review_item_id"]))
    reasons = {reason["reason"] for reason in json_loads(item["metadata_json"])["reasons"]}
    assert {"low_confidence", "schema_error", "business_rule", "business_validation"} <= reasons


@pytest.mark.parametrize("change", ["extraction", "source"])
def test_gate_rejects_source_race_before_persisting_report(review, monkeypatch, change):
    import modules.services.review_service as runtime
    original = runtime.build_business_report
    def race(*args, **kwargs):
        report = original(*args, **kwargs)
        with closing(connect(review["config"])) as other:
            if change == "extraction":
                ExtractionRepository(other).save_result(document_id=review["context"]["document_id"], provider="retry", data={})
            else:
                DocumentRepository(other).add_file(document_id=review["context"]["document_id"],
                    file_type="split_pdf", file_path="synthetic-replacement.pdf")
        return report
    monkeypatch.setattr(runtime, "build_business_report", race)
    with pytest.raises(TaskError, match="incompatible"):
        review["task"].run(review["context"])


def test_passing_gate_report_is_durable_without_review_item(tmp_path):
    config = TempConfig(tmp_path / "state.sqlite3")
    initialize_database(config)
    seeded = seed_business_review(config, tmp_path, values=good_values())
    result = seeded["task"].run(seeded["context"])
    assert result["review_gate_status"] == "passed"
    with closing(connect(config)) as conn:
        assert conn.execute("SELECT count(*) FROM review_items").fetchone()[0] == 0
        report = json_loads(require_present(DocumentRepository(conn).get(result["document_id"]))["metadata_json"])["business_validation"]["gate"]
        assert all(check["status"] == "passed" for check in report["checks"])


def test_explicit_null_correction_is_preserved_in_detail(review):
    ExtractionRepository(review["conn"]).apply_corrections(review["context"]["document_id"], {"subtotal": None})
    field = next(field for field in detail(review)["fields"] if field["field_key"] == "subtotal")
    assert field["has_correction"] and field["corrected_value"] is None and field["final_value"] is None
