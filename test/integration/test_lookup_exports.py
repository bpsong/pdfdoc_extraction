"""Verify real lookup releases, reviewed continuations, and registered exports."""

from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfReader, PdfWriter

from modules.db.connection import json_loads, managed_connect
from modules.db.repositories import DocumentRepository, ExtractionRepository, LookupKey, ReviewRepository, TaskRunRepository
from modules.resume_manager import ResumeManager
from modules.services.lookup_decision_service import LookupDecisionService
from modules.services.manual_split_service import ManualSplitReviewService
from modules.services.processing_worker import ProcessingWorker
from modules.services.review_service import ReviewBusinessError, ReviewService
from modules.services.startup_migration_service import initialize_database
from test.helpers_assertions import require_present
from test.helpers_business_validation_workflow import offline_invoice_workflows, write_synthetic_pdf
from test.helpers_sqlite import TempConfig
from test.integration.test_lookup_pipeline import _add_gate, _definition, _document, _publish


INVOICE = {"tax": "00123", "supplier": "acme"}
UNIQUE_REGISTER = b"Tax,Name,Code\n00123,Acme,00042\n"
AMBIGUOUS_REGISTER = b"Tax,Name,Code\n00123,Acme,00041\n00123,ACME,00042\n"


@pytest.fixture
def config(tmp_path: Path) -> TempConfig:
    deployment = TempConfig(tmp_path / "state.sqlite3", {
        "watch_folder": {"processing_dir": str(tmp_path / "processing")},
        "pipeline_secrets": {"extract": "synthetic-unused-value"},
    })
    initialize_database(deployment)
    return deployment


def lookup_export_definition(root: Path, *, required: bool = True) -> dict[str, Any]:
    """Configure the same real storage tasks for automatic and reviewed release."""
    definition = _definition(root)
    lookup = definition["tasks"]["lookup"]["params"]
    lookup.update(required=required, on_no_match="review" if required else "continue", on_multiple_matches="review")
    output = str(root / "exports")
    filename = "{supplier_id}_{id}" if required else "{tax}_{id}"
    definition["tasks"]["output"]["params"]["filename"] = filename
    definition["tasks"].update({
        "csv": {"module": "standard_step.storage.store_metadata_as_csv", "class": "StoreMetadataAsCsv",
                "params": {"data_dir": output, "filename": filename}},
        "pdf": {"module": "standard_step.storage.store_file_to_localdrive", "class": "StoreFileToLocaldrive",
                "params": {"files_dir": output, "filename": filename}},
    })
    definition["pipeline"].extend(["csv", "pdf"])
    return definition


def assert_lookup_exports(
    config: TempConfig, document_id: str, version_id: str, output: Path, source_pdf: bytes,
    expected: dict[str, Any], *, filename_value: str,
) -> dict[str, Any]:
    """Check the exact payload, registered artifact ownership, and copied PDF."""
    types = {"export_json": (".json", "output"), "export_csv": (".csv", "csv"), "export_pdf": (".pdf", "pdf")}
    with managed_connect(config) as conn:
        documents = DocumentRepository(conn)
        document = require_present(documents.get(document_id))
        assert document["status"] == "completed" and document["pipeline_version_id"] == version_id
        exports = [entry for entry in documents.list_files(document_id) if entry["file_type"].startswith("export_")]
        assert sorted(entry["file_type"] for entry in exports) == sorted(types)
        runs = TaskRunRepository(conn).list_by_document(document_id)
        assert {run["pipeline_version_id"] for run in runs} == {version_id}
        for entry in exports:
            suffix, task_key = types[entry["file_type"]]
            assert entry["document_id"] == document_id
            assert Path(entry["file_path"]) == output / f"{filename_value}_{document_id}{suffix}"
            assert json_loads(entry["metadata_json"])["task_key"] == task_key
            assert [run["status"] for run in runs if run["task_key"] == task_key] == ["completed"]
        json_entry = next(entry for entry in exports if entry["file_type"] == "export_json")
        json_run = next(run for run in runs if run["task_key"] == "output")
        assert json_loads(json_entry["metadata_json"])["task_run_id"] == json_run["id"]
    stem = output / f"{filename_value}_{document_id}"
    payload = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
    assert payload == expected
    with stem.with_suffix(".csv").open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == [{key: str(value) for key, value in expected.items()}]
    assert stem.with_suffix(".pdf").read_bytes() == source_pdf
    return payload


def _invoice_case(config: TempConfig, root: Path, version: dict[str, Any]) -> dict[str, Any]:
    source = root / "synthetic-invoice.pdf"
    write_synthetic_pdf(source, ["SYNTHETIC INVOICE - TEST DATA ONLY", "Tax ID: 00123", "Supplier: Acme"])
    return _document(config, root, version, source=source)


def _assert_held(config: TempConfig, root: Path, document_id: str) -> None:
    with managed_connect(config) as conn:
        assert not any(file["file_type"].startswith("export_") for file in DocumentRepository(conn).list_files(document_id))
        assert not {"output", "csv", "pdf"} & {run["task_key"] for run in TaskRunRepository(conn).list_by_document(document_id)}
    assert not list((root / "exports").glob(f"*_{document_id}.*"))


def _review(config: TempConfig, document_id: str) -> str:
    with managed_connect(config) as conn:
        return require_present(ReviewRepository(conn).find_latest_for_document(document_id, review_kind="extraction"))["id"]


def _pick(token: str, record: int) -> dict[str, Any]:
    return {"action": "select", "evaluation_token": token, "record_number": record, "reason": "Checked synthetic invoice"}


def test_unique_and_reviewed_match_release_identical_text_and_registered_files(config: TempConfig, tmp_path: Path) -> None:
    reference = tmp_path / "register.csv"
    reference.write_bytes(UNIQUE_REGISTER)
    definition = lookup_export_definition(tmp_path)
    _add_gate(config, definition)
    version = _publish(config, definition)
    automatic = _invoice_case(config, tmp_path / "automatic", version)
    review = _invoice_case(config, tmp_path / "review", version)
    automatic_id, reviewed_id = (case["document"]["id"] for case in (automatic, review))
    expected = {**INVOICE, "supplier_id": "00042"}
    output = tmp_path / "exports"

    with offline_invoice_workflows(INVOICE) as extractions:
        worker = ProcessingWorker(config)
        assert worker.run_once()
        direct = assert_lookup_exports(config, automatic_id, version["id"], output,
                                       automatic["source"].read_bytes(), expected, filename_value="00042")
        assert reference.read_bytes() == UNIQUE_REGISTER
        # Replace the fixture between documents while keeping the definition and invoice identical.
        reference.write_bytes(AMBIGUOUS_REGISTER)
        assert worker.run_once()
        assert not worker.run_once()
        _assert_held(config, tmp_path, reviewed_id)
        review_id = _review(config, reviewed_id)
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            service.claim(review_id, "operator")
            detail = require_present(service.get_detail(review_id))
            lookup = detail["lookup_review"]["lookups"][0]
            assert lookup["outcome"] == "multiple_matches"
            pending_id = lookup["decision_id"]
            request = {"expected_revision": detail["review_revision"],
                       "lookup_actions": {"lookup": _pick(lookup["evaluation_token"], 2)}}
            checked = service.revalidate(review_id, "operator", {}, **request)
            service.complete(review_id, "operator", {}, lookup_preview_token=checked["lookup_review"]["preview_token"],
                             trigger_resume=False, **request)
            accepted = require_present(service.get_detail(review_id))["metadata"]["lookup_acceptance"]
            decision = require_present(LookupDecisionService(conn).current(LookupKey(reviewed_id, version["id"], "lookup")))
            assert accepted["decision_ids"] == {"lookup": decision.id}
            assert decision.id != pending_id and decision.supersedes_id == pending_id
        _assert_held(config, tmp_path, reviewed_id)
        resume = ResumeManager(config)
        assert resume.resume_document(reviewed_id, user="operator")
        assert not resume.resume_document(reviewed_id, user="operator")
        assert [call["document_id"] for call in extractions] == [automatic_id, reviewed_id]

    reviewed = assert_lookup_exports(config, reviewed_id, version["id"], output,
                                     review["source"].read_bytes(), expected, filename_value="00042")
    assert reviewed == direct
    assert len(list(output.iterdir())) == 6
    assert reference.read_bytes() == AMBIGUOUS_REGISTER
    with managed_connect(config) as conn:
        repository = ExtractionRepository(conn)
        for document_id in (automatic_id, reviewed_id):
            assert json_loads(require_present(repository.get_latest_result(document_id))["data_json"]) == INVOICE
            assert {field["field_key"] for field in repository.get_fields(document_id)} == INVOICE.keys()
        assert ReviewRepository(conn).find_latest_for_document(automatic_id) is None


@pytest.mark.parametrize("required", [False, True], ids=["optional-miss", "required-miss"])
def test_missing_lookup_only_releases_for_optional_policy(config: TempConfig, tmp_path: Path, required: bool) -> None:
    reference = tmp_path / "register.csv"
    register = b"Tax,Name,Code\n00444,Acme,00044\n"
    reference.write_bytes(register)
    definition = lookup_export_definition(tmp_path, required=required)
    _add_gate(config, definition)
    version = _publish(config, definition)
    case = _invoice_case(config, tmp_path, version)
    document_id = case["document"]["id"]
    with offline_invoice_workflows(INVOICE):
        assert ProcessingWorker(config).run_once()
    if required:
        review_id = _review(config, document_id)
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            service.claim(review_id, "operator")
            detail = require_present(service.get_detail(review_id))
            request = {"expected_revision": detail["review_revision"]}
            preview = service.revalidate(review_id, "operator", {}, **request)["lookup_review"]
            assert preview["blocked"] and preview["lookups"][0]["outcome"] == "no_match"
            with pytest.raises(ReviewBusinessError, match="Resolve the CSV lookup") as failure:
                service.complete(review_id, "operator", {}, lookup_preview_token=preview["preview_token"], **request)
            assert failure.value.detail["code"] == "lookup_review_blocked"
            assert "lookup_acceptance" not in require_present(service.get_detail(review_id))["metadata"]
        _assert_held(config, tmp_path, document_id)
    else:
        assert_lookup_exports(config, document_id, version["id"], tmp_path / "exports",
                              case["source"].read_bytes(), INVOICE, filename_value=INVOICE["tax"])
        with managed_connect(config) as conn:
            assert ReviewRepository(conn).find_latest_for_document(document_id) is None
            decision = require_present(LookupDecisionService(conn).current(LookupKey(document_id, version["id"], "lookup")))
            assert decision.state == "skipped" and decision.returned_values() == {}
    assert reference.read_bytes() == register


def test_repaired_register_and_business_rules_require_current_acceptance(config: TempConfig, tmp_path: Path) -> None:
    reference = tmp_path / "register.csv"
    original = b"Tax,Name,Code\n00444,Acme,00044\n"
    reference.write_bytes(original)
    definition = lookup_export_definition(tmp_path)
    definition["tasks"]["extract"]["params"]["fields"]["approval"] = {"type": "str", "alias": "Approval"}
    _add_gate(config, definition, review_scope="document", schema={
        "fields": {"tax": {"type": "string"}, "supplier_id": {"type": "string"}, "approval": {"type": "string"}},
        "business_validation": {"format_version": 1, "rules": [
            {"id": "supplier_approval", "validator": "required_if:v1", "when": "/supplier_id", "equals": "00042",
             "required": ["/approval"], "severity": "blocking"},
        ]},
    })
    version = _publish(config, definition)
    case = _invoice_case(config, tmp_path, version)
    document_id = case["document"]["id"]
    extracted = {**INVOICE, "tax": "wrong", "approval": ""}
    final_register = b"Tax,Name,Code\n00123,Acme,00057\n"
    with offline_invoice_workflows(extracted) as extractions:
        assert ProcessingWorker(config).run_once()
        review_id = _review(config, document_id)
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            service.claim(review_id, "operator")
            detail = require_present(service.get_detail(review_id))
            initial = detail["lookup_review"]["lookups"][0]
            revision = detail["review_revision"]
            assert initial["source_sha256"] == sha256(original).hexdigest()
            reference.write_bytes(UNIQUE_REGISTER)
            corrections = {"tax": "00123"}
            preview = service.revalidate(review_id, "operator", corrections, expected_revision=revision)
            assert preview["lookup_review"]["lookups"][0]["issue"] == "reference_changed"
            request = {"expected_revision": revision, "reference_adoptions": {"lookup": "Approved repaired synthetic register"}}
            preview = service.revalidate(review_id, "operator", corrections, **request)
            assert not preview["lookup_review"]["blocked"] and preview["business_validation"]["has_blocking_findings"]
            with pytest.raises(ReviewBusinessError, match="blocking business") as blocked:
                service.complete(review_id, "operator", corrections, lookup_preview_token=preview["lookup_review"]["preview_token"], **request)
            assert blocked.value.detail["code"] == "business_validation_blocked"
            _assert_held(config, tmp_path, document_id)
            corrections["approval"] = "APPROVED"
            preview = service.revalidate(review_id, "operator", corrections, **request)
            assert not preview["business_validation"]["has_blocking_findings"]
            reference.write_bytes(final_register)
            with pytest.raises(ReviewBusinessError, match="Revalidate") as stale:
                service.complete(review_id, "operator", corrections, lookup_preview_token=preview["lookup_review"]["preview_token"], **request)
            assert stale.value.detail["code"] == "stale_lookup_preview"
            assert "lookup_acceptance" not in require_present(service.get_detail(review_id))["metadata"]
            _assert_held(config, tmp_path, document_id)
            fresh = service.revalidate(review_id, "operator", corrections, **request)
            service.complete(review_id, "operator", corrections, lookup_preview_token=fresh["lookup_review"]["preview_token"],
                             trigger_resume=False, **request)
            accepted = require_present(service.get_detail(review_id))["metadata"]
            decision_id = accepted["lookup_acceptance"]["decision_ids"]["lookup"]
            decision = require_present(LookupDecisionService(conn).current(LookupKey(document_id, version["id"], "lookup")))
            assert decision.id == decision_id and decision.supersedes_id == initial["decision_id"]
            assert decision.evaluation.source_sha256 == sha256(final_register).hexdigest()
            assert decision.reason == request["reference_adoptions"]["lookup"]
            assert accepted["business_validation"]["accepted"]["lookup_sources"]["lookup"]["decision_id"] == decision_id
        # Later file contents do not replace the accepted decision on resume.
        reference.write_bytes(UNIQUE_REGISTER)
        assert ResumeManager(config).resume_document(document_id, user="operator")
        assert len(extractions) == 1
    assert_lookup_exports(config, document_id, version["id"], tmp_path / "exports", case["source"].read_bytes(),
                          {**INVOICE, "approval": "APPROVED", "supplier_id": "00057"}, filename_value="00057")
    assert reference.read_bytes() == UNIQUE_REGISTER
    with managed_connect(config) as conn:
        assert json_loads(require_present(ExtractionRepository(conn).get_latest_result(document_id))["data_json"]) == extracted


def test_split_children_release_distinct_suppliers_from_pinned_lookup(config: TempConfig, tmp_path: Path) -> None:
    reference = tmp_path / "register.csv"
    register = AMBIGUOUS_REGISTER + b"00444,Beta,00088\n"
    reference.write_bytes(register)
    definition = lookup_export_definition(tmp_path)
    _add_gate(config, definition)
    definition["pipeline"].insert(0, "split")
    definition["tasks"]["split"] = {"module": "standard_step.split.manual_split", "class": "ManualSplitTask",
                                     "params": {"split_dir": str(tmp_path / "split")}}
    version = _publish(config, definition)
    source = tmp_path / "synthetic-bundle.pdf"
    writer = PdfWriter()
    for width in (200, 300):
        writer.add_blank_page(width=width, height=400)
    writer.write(source)
    root = _document(config, tmp_path, version, source=source)["document"]
    second_invoice = {"tax": "00444", "supplier": "beta"}

    def read_synthetic_child(context: dict[str, Any]) -> dict[str, Any]:
        return {200: INVOICE, 300: second_invoice}[int(PdfReader(context["file_path"]).pages[0].mediabox.width)]

    with offline_invoice_workflows(read_synthetic_child) as extractions:
        assert ProcessingWorker(config).run_once()
        with managed_connect(config) as conn:
            split_review = require_present(ReviewRepository(conn).find_latest_for_document(root["id"], review_kind="manual_split"))
            ReviewService(conn, config).claim(split_review["id"], "operator")
            ManualSplitReviewService(conn, config).save(split_review["id"], "operator", {
                "boundaries": [1], "action": "split", "expected_revision": 1,
            }, complete=True)
        assert ResumeManager(config).resume_document(root["id"], user="operator")
        with managed_connect(config) as conn:
            documents = DocumentRepository(conn)
            first, second = sorted(documents.list_children(root["id"]), key=lambda item: item["page_start"])
            assert [first["status"], second["status"]] == ["review_required", "completed"]
            assert [first["page_start"], second["page_start"]] == [1, 2]
            assert {call["document_id"] for call in extractions} == {first["id"], second["id"]}
            assert len(extractions) == 2
            lookup_service = LookupDecisionService(conn)
            assert lookup_service.current(LookupKey(root["id"], version["id"], "lookup")) is None
            second_decision = require_present(lookup_service.current(LookupKey(second["id"], version["id"], "lookup")))
            assert second_decision.returned_values() == {"supplier_id": "00088"}
            assert not any(file["file_type"].startswith("export_") for file in documents.list_files(root["id"]))
            _assert_held(config, tmp_path, first["id"])
        review_id = _review(config, first["id"])
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            service.claim(review_id, "operator")
            detail = require_present(service.get_detail(review_id))
            lookup = detail["lookup_review"]["lookups"][0]
            assert [record["values"] for record in lookup["candidates"]] == [{"supplier_id": "00041"}, {"supplier_id": "00042"}]
            request = {"expected_revision": detail["review_revision"],
                       "lookup_actions": {"lookup": _pick(lookup["evaluation_token"], 2)}}
            preview = service.revalidate(review_id, "operator", {}, **request)["lookup_review"]
            assert service.complete(review_id, "operator", {}, lookup_preview_token=preview["preview_token"], **request)["resume_triggered"]

    for item, invoice, code in [(first, INVOICE, "00042"), (second, second_invoice, "00088")]:
        assert_lookup_exports(config, item["id"], version["id"], tmp_path / "exports", Path(item["file_path"]).read_bytes(),
                              {**invoice, "supplier_id": code}, filename_value=code)
    assert len(list((tmp_path / "exports").iterdir())) == 6
    assert reference.read_bytes() == register
    with managed_connect(config) as conn:
        assert require_present(DocumentRepository(conn).get(root["id"]))["status"] == "completed"
        current = require_present(LookupDecisionService(conn).current(LookupKey(second["id"], version["id"], "lookup")))
        assert current.id == second_decision.id
