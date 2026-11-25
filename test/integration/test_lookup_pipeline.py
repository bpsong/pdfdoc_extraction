"""Exercise real publication, pinned execution, and release checks for R3."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pypdf import PdfWriter

from modules.db.connection import json_loads, managed_connect
from modules.db.repositories import ExtractionRepository, LookupKey, ReviewRepository
from modules.services.csv_reference_lookup import CSV_LOOKUP_TASK
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.lookup_decision_service import LookupDecisionService
from modules.services.pipeline_definition_service import PipelineDefinitionService
from modules.services.pipeline_template_service import PipelineTemplateService, PipelineTemplateValidationError
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.startup_migration_service import initialize_database
from modules.services.task_catalog_service import TaskCatalogService
from modules.services.validation_facade import ValidationFacade
from modules.services.versioned_admin_service import VersionedAdminService
from test.helpers_business_validation_workflow import offline_invoice_workflows, run_invoice_workflow
from test.helpers_sqlite import TempConfig
from tools.config_check.validator import ConfigValidator


@pytest.fixture
def deployment(tmp_path: Path) -> TempConfig:
    config = TempConfig(tmp_path / "state.sqlite3", {"pipeline_secrets": {"extract": "test-value"}})
    initialize_database(config)
    return config


def _definition(root: Path) -> dict[str, Any]:
    return {"schema_version": 1, "pipeline": ["extract", "lookup", "output"], "tasks": {
        "extract": {
            "module": "standard_step.extraction.extract_pdf", "class": "ExtractPdfTask",
            "params": {"api_key": {"$secret": "extract"}, "fields": {
                "tax": {"type": "str", "alias": "Tax"},
                "supplier": {"type": "str", "alias": "Supplier"},
            }},
        },
        "lookup": {
            "module": CSV_LOOKUP_TASK[0], "class": CSV_LOOKUP_TASK[1], "on_error": "stop",
            "params": {"reference_file": "register.csv",
                       "clauses": [{"field": "tax", "column": "Tax"},
                                   {"field": "supplier", "column": "Name", "mode": "case_insensitive"}],
                       "returns": [{"field": "supplier_id", "column": "Code"}],
                       "on_no_match": "fail", "on_multiple_matches": "fail"},
        },
        "output": {
            "module": "standard_step.storage.store_metadata_as_json", "class": "StoreMetadataAsJson",
            "params": {"data_dir": str(root / "exports"), "filename": "{supplier_id}_{id}"},
        },
    }}


def _add_gate(
    config: TempConfig, definition: dict[str, Any], *, schema: dict[str, Any] | None = None, **params: Any,
) -> None:
    with managed_connect(config) as conn:
        service = ReviewSchemaVersionService(conn)
        form = service.create_template(
            schema_key="supplier-review", name="Supplier review", user="admin",
            initial_schema=schema or {"schema_version": 1, "fields": {"tax": {"type": "string"}}},
        )["template"]
        version = service.publish(form["id"], expected_revision=1, user="admin")["version"]
        service.update_template(form["id"], status="active", user="admin")
    definition["pipeline"].insert(2, "gate")
    definition["tasks"]["gate"] = {
        "module": "standard_step.review.review_gate", "class": "ReviewGateTask",
        "params": {"schema_version_id": version["id"], **params},
    }


def _publish(config: TempConfig, definition: dict[str, Any]) -> dict[str, Any]:
    with managed_connect(config) as conn:
        service = PipelineTemplateService(
            conn, validation=ValidationFacade(config), configured_secret_aliases={"extract"},
        )
        template = service.create_template(template_key="reference", name="Reference", user="admin",
                                           initial_definition=definition)["template"]
        result = service.validate_draft(template["id"], user="admin")
        assert result["valid"], result
        version = service.publish(template["id"], expected_revision=1, user="admin")["version"]
        service.update_template(template["id"], status="active", user="admin")
    return version


def _document(config: TempConfig, root: Path, version: dict[str, Any], *, source: Path | None = None) -> dict[str, Any]:
    if source is None:
        source = root / "invoice.pdf"
        pdf = PdfWriter()
        pdf.add_blank_page(width=200, height=200)
        pdf.write(source)
    with managed_connect(config) as conn:
        assigned = IngestionAssignmentService(conn, config).create_batch(
            pipeline_version_id=version["id"], role="operator", source="web", assignment_source="upload",
            files=[{"file_path": str(source), "original_filename": source.name, "status": "queued"}],
            user="operator",
        )
    return {"document": assigned["documents"][0], "source": source}


def test_published_lookup_resolves_worker_file_and_exports_pinned_text(
    deployment: TempConfig, tmp_path: Path,
) -> None:
    definition = _definition(tmp_path)
    version = _publish(deployment, definition)
    assert any(
        finding["code"] == "lookup-reference-unavailable"
        for finding in version["validation_summary"]["findings"]
    )
    # The register is deployed to the worker after publication.
    register = tmp_path / "register.csv"
    original = b"Tax,Name,Code\n00123,ACME,00042\n123,Acme,WRONG\n"
    register.write_bytes(original)
    case = _document(deployment, tmp_path, version)
    with managed_connect(deployment) as conn:
        admin = VersionedAdminService(conn, configured_secret_aliases={"extract"})
        bundle = json.loads(admin.export_pipeline_version(version["template_id"], version["id"], format="json"))
        imported = admin.import_pipeline_document(bundle)
        assert imported == definition
        template = admin.pipelines.create_template(template_key="imported", name="Imported", user="admin")["template"]
        saved = admin.pipelines.import_draft(template["id"], expected_revision=1, definition=imported, user="admin")
        assert saved["definition"] == definition

        changed = deepcopy(definition)
        changed["tasks"]["lookup"]["params"]["reference_file"] = "different.csv"
        revision = admin.pipelines.drafts.get(version["template_id"])
        assert revision is not None
        admin.pipelines.save_draft(version["template_id"], expected_revision=revision["revision"],
                                   definition=changed, user="admin")
        loaded = PipelineDefinitionService(conn, deployment).load_for_document(case["document"]["id"])
        assert loaded.tasks["lookup"]["params"]["reference_file"] == "register.csv"

    with offline_invoice_workflows({"tax": "00123", "supplier": "acme"}):
        result = run_invoice_workflow(deployment, case)
    assert not result["error"], result.get("error")
    assert result["data"] == {"tax": "00123", "supplier": "acme", "supplier_id": "00042"}
    paths = list((tmp_path / "exports").glob("00042_*.json"))
    assert len(paths) == 1
    assert json.loads(paths[0].read_text(encoding="utf-8")) == result["data"]
    with managed_connect(deployment) as conn:
        document_id = case["document"]["id"]
        saved = ExtractionRepository(conn).get_latest_result(document_id)
        assert saved is not None and json_loads(saved["data_json"]) == {"tax": "00123", "supplier": "acme"}
        decision = LookupDecisionService(conn).current(LookupKey(document_id, version["id"], "lookup"))
        assert decision is not None and decision.returned_values() == {"supplier_id": "00042"}
    assert register.read_bytes() == original


@pytest.mark.parametrize(("variant", "code"), [
    ("before-extraction", "lookup-before-extraction"),
    ("after-release", "lookup-after-release"),
    ("optional-after-release", "lookup-after-release"),
    ("no-gate", "lookup-review-gate-order"),
    ("optional-filename", "lookup-filename-dependency"),
    ("field-collision", "lookup-field-collision"),
    ("reserved-field", "lookup-invalid-parameters"),
    ("numeric-as-text", "lookup-source-type"),
    ("continue-on-error", "lookup-on-error"),
    ("bad-header", "lookup-reference-invalid"),
    ("secret-path", "lookup-invalid-parameters"),
    ("chained", "lookup-source-field"),
    ("later-extraction", "lookup-source-field"),
    ("later-extraction-with-undeclared-earlier-fields", "lookup-source-field"),
])
def test_publication_rejects_invalid_lookup_bindings(
    deployment: TempConfig, tmp_path: Path, variant: str, code: str,
) -> None:
    definition = _definition(tmp_path)
    settings = definition["tasks"]["lookup"]["params"]
    if variant == "before-extraction":
        definition["pipeline"] = ["lookup", "extract", "output"]
    elif variant in ("after-release", "optional-after-release"):
        definition["pipeline"] = ["extract", "output", "lookup"]
        if variant == "optional-after-release":
            settings["required"] = False
            settings["on_no_match"] = "continue"
            definition["tasks"]["output"]["params"]["filename"] = "{tax}"
    elif variant == "no-gate":
        settings["on_multiple_matches"] = "review"
    elif variant == "optional-filename":
        settings["required"] = False
    elif variant == "field-collision":
        definition["tasks"]["extract"]["params"]["fields"]["supplier_id"] = {"type": "str", "alias": "Supplier ID"}
    elif variant == "reserved-field":
        settings["returns"][0]["field"] = "id"
    elif variant == "numeric-as-text":
        definition["tasks"]["extract"]["params"]["fields"]["tax"]["type"] = "int"
    elif variant == "continue-on-error":
        definition["tasks"]["lookup"]["on_error"] = "continue"
    elif variant == "bad-header":
        (tmp_path / "register.csv").write_text("Tax,Name,Wrong\n", encoding="utf-8")
    elif variant == "secret-path":
        settings["reference_file"] = {"$secret": "extract"}
    elif variant == "chained":
        second = deepcopy(definition["tasks"]["lookup"])
        second["params"]["returns"][0]["field"] = "another_id"
        second["params"]["clauses"][0]["field"] = "supplier_id"
        definition["tasks"]["second"] = second
        definition["pipeline"].insert(2, "second")
    elif variant.startswith("later-extraction"):
        definition["tasks"]["later"] = deepcopy(definition["tasks"]["extract"])
        definition["tasks"]["later"]["params"]["fields"]["future_tax"] = {"type": "str", "alias": "Future tax"}
        if variant.endswith("earlier-fields"):
            del definition["tasks"]["extract"]["params"]["fields"]
        settings["clauses"][0]["field"] = "future_tax"
        definition["pipeline"].insert(2, "later")
    with managed_connect(deployment) as conn:
        service = PipelineTemplateService(conn, validation=ValidationFacade(deployment),
                                          configured_secret_aliases={"extract"})
        template = service.create_template(template_key="invalid", name="Invalid", user="admin",
                                           initial_definition=definition)["template"]
        draft = service.validate_draft(template["id"], user="admin")
        assert any(finding["code"] == code for finding in draft["findings"]), draft
        with pytest.raises(PipelineTemplateValidationError):
            service.publish(template["id"], expected_revision=1, user="admin")


@pytest.mark.parametrize("variant", [
    "malformed", "removed", "collision", "pending", "downstream-review",
    "optional-miss", "required-miss", "passing-gate",
])
def test_worker_handles_lookup_outcomes_at_the_release_boundary(
    deployment: TempConfig, tmp_path: Path, variant: str,
) -> None:
    definition = _definition(tmp_path)
    settings = definition["tasks"]["lookup"]["params"]
    register = tmp_path / "register.csv"
    register.write_text("Tax,Name,Code\n00123,ACME,00042\n", encoding="utf-8")
    data = {"tax": "00123", "supplier": "acme"}
    if variant in ("malformed", "removed", "optional-miss"):
        settings.update(required=False, on_no_match="continue")
        definition["tasks"]["output"]["params"]["filename"] = "{tax}"
    if variant == "pending":
        settings["on_multiple_matches"] = "review"
        _add_gate(deployment, definition)
    elif variant == "downstream-review":
        _add_gate(deployment, definition, always_review=True)
        definition["tasks"]["gate"]["on_error"] = "continue"
    elif variant == "passing-gate":
        settings["on_multiple_matches"] = "review"
        _add_gate(deployment, definition)
    version = _publish(deployment, definition)
    if variant == "removed":
        register.unlink()
    elif variant == "malformed":
        register.write_text('Tax,Name,Code\n00123,ACME,"unclosed\n', encoding="utf-8")
    elif variant == "collision":
        data["supplier_id"] = "from extraction"
    elif variant == "pending":
        register.write_text("Tax,Name,Code\n00123,ACME,00042\n00123,Acme,00043\n", encoding="utf-8")
    elif variant in ("optional-miss", "required-miss"):
        data["tax"] = "new"

    case = _document(deployment, tmp_path, version)
    with offline_invoice_workflows(data):
        result = run_invoice_workflow(deployment, case)
    if variant == "optional-miss":
        assert not result["error"]
        assert "supplier_id" not in result["data"]
        assert len(list((tmp_path / "exports").glob("*.json"))) == 1
    elif variant == "passing-gate":
        assert not result["error"]
        assert result["data"]["supplier_id"] == "00042"
        assert len(list((tmp_path / "exports").glob("*.json"))) == 1
    elif variant in ("pending", "downstream-review"):
        assert result["pipeline_state"] == "paused"
        assert not list((tmp_path / "exports").glob("*.json"))
    else:
        assert result["error"]
        assert not list((tmp_path / "exports").glob("*.json"))
    with managed_connect(deployment) as conn:
        document_id = case["document"]["id"]
        decision = LookupDecisionService(conn).current(LookupKey(document_id, version["id"], "lookup"))
        expected = {
            "pending": "pending", "downstream-review": "matched", "optional-miss": "skipped",
            "required-miss": "failed", "passing-gate": "matched",
        }.get(variant)
        assert (decision.state if decision else None) == expected
        review = ReviewRepository(conn).find_latest_for_document(document_id)
        assert bool(review) == (variant in ("pending", "downstream-review"))


def test_config_check_and_backend_catalog_keep_lookup_and_update_distinct(
    deployment: TempConfig, tmp_path: Path,
) -> None:
    configuration = _definition(tmp_path)
    configuration["tasks"]["extract"]["params"]["api_key"] = "synthetic"
    configuration["watch_folder"] = {"dir": str(tmp_path), "processing_dir": str(tmp_path)}
    configuration["web"] = {"upload_dir": str(tmp_path), "secret_key": "synthetic-config-check-key"}
    (tmp_path / "exports").mkdir()
    register = tmp_path / "register.csv"
    register.write_text("Tax,Name,Code\n", encoding="utf-8")
    path = tmp_path / "check.yaml"
    path.write_text(yaml.safe_dump(configuration), encoding="utf-8")
    result = ConfigValidator(check_files=True, import_checks=True).validate(path)
    assert result.is_valid, [(error.path, error.code) for error in result.errors]
    register.write_text("Tax,Name,Code\nrow,wrong-column-count\n", encoding="utf-8")
    result = ConfigValidator(check_files=True).validate(path)
    assert any(error.code == "lookup-reference-invalid" for error in result.errors)
    register.unlink()
    structural = ConfigValidator().validate(path)
    assert any(warning.code == "lookup-reference-unavailable" for warning in structural.warnings)
    local = ConfigValidator(check_files=True).validate(path)
    assert any(error.code == "lookup-reference-invalid" for error in local.errors)
    catalog = TaskCatalogService(deployment)
    tasks = {task["class_name"]: task for task in catalog.catalog()["tasks"]}
    assert tasks[CSV_LOOKUP_TASK[1]]["import_status"] == "ok"
    assert tasks["UpdateReferenceTask"]["import_status"] == "ok"
    assert CSV_LOOKUP_TASK[1] not in {entry["class_name"] for entry in catalog.catalog(include_preview=False)["tasks"]}


def test_independent_lookups_and_legacy_csv_update_run_in_one_pipeline(
    deployment: TempConfig, tmp_path: Path,
) -> None:
    definition = _definition(tmp_path)
    (tmp_path / "register.csv").write_text("Tax,Name,Code\n00123,ACME,00042\n", encoding="utf-8")
    independent = deepcopy(definition["tasks"]["lookup"])
    independent["params"]["returns"][0]["field"] = "billing_id"
    definition["tasks"]["billing"] = independent
    legacy = tmp_path / "legacy.csv"
    legacy.write_text("Tax,Status\n00123,New\n", encoding="utf-8")
    definition["tasks"]["legacy"] = {
        "module": "standard_step.rules.update_reference", "class": "UpdateReferenceTask",
        "params": {"reference_file": str(legacy), "update_field": "Status", "write_value": "Updated",
                   "backup": False, "csv_match": {"type": "column_equals_all", "clauses": [
                       {"column": "Tax", "from_context": "tax", "number": False},
                   ]}},
    }
    definition["pipeline"] = ["extract", "lookup", "billing", "legacy", "output"]
    version = _publish(deployment, definition)
    case = _document(deployment, tmp_path, version)
    with offline_invoice_workflows({"tax": "00123", "supplier": "acme"}):
        result = run_invoice_workflow(deployment, case)
    assert not result["error"], result.get("error")
    assert (result["data"]["supplier_id"], result["data"]["billing_id"]) == ("00042", "00042")
    assert "Updated" in legacy.read_text(encoding="utf-8")
