"""Rule authoring, persistence, dependency, and startup compatibility checks."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from test.helpers_assertions import require_present

from modules.db.connection import connect
from modules.services.business_validation_schema import validate_business_validation_schema
from modules.services.review_schema_version_service import (
    ReviewSchemaValidationError, ReviewSchemaVersionService,
)
from modules.services.schema_service import SchemaService
from modules.services.startup_migration_service import initialize_database
from modules.services.startup_service import (
    StartupReadinessError, verify_business_validation_compatibility,
)
from modules.services.validation_facade import ValidationFacade
from modules.services.versioned_config_contracts import ValidationSource, content_hash
from test.helpers_business_validation import invoice_review_schema
from test.helpers_sqlite import TempConfig
from tools.config_check.stored_validator import validate_portable_file


def test_valid_and_legacy_forms_are_unchanged() -> None:
    schema = invoice_review_schema()
    original = deepcopy(schema)
    assert validate_business_validation_schema(schema) == []
    assert schema == original
    del schema["business_validation"]
    assert validate_business_validation_schema(schema) == []


@pytest.mark.parametrize(("property", "value"), [
    ("collection", "/missing"), ("collection", "/subtotal"),
    ("quantity", "/description"), ("quantity", "/missing"),
    ("unit_price", "/unit_price/value"), ("line_total", "line_total"),
    ("validator", "unavailable:v2"), ("tolerance", "-1"),
])
def test_invalid_or_disabled_bindings_block_publication_validation(
    property: str, value: Any,
) -> None:
    schema = invoice_review_schema()
    schema["business_validation"]["rules"][0].update({property: value, "enabled": False})
    findings = SchemaService(TempConfig(Path("unused.sqlite3"))).validate_schema(schema)
    assert findings
    assert any(finding["path"].startswith("business_validation") for finding in findings)


@pytest.mark.parametrize("section", [None, [], {"format_version": 2}, {"rules": "invalid"}])
def test_present_invalid_section_is_not_treated_as_no_rules(section: Any) -> None:
    schema = invoice_review_schema()
    schema["business_validation"] = section
    assert validate_business_validation_schema(schema)


def test_subtotal_target_requires_a_document_numeric_field() -> None:
    schema = invoice_review_schema()
    schema["business_validation"]["rules"][1]["target"] = "/items"
    assert validate_business_validation_schema(schema) == [{
        "path": "business_validation.rules.1.target",
        "message": "Select an existing numeric field in the indicated scope.",
    }]


def test_nested_escaped_collection_and_numeric_array_index_bindings() -> None:
    schema = invoice_review_schema()
    original = invoice_review_schema()["fields"]
    schema["fields"] = {"a/b~": {"type": "object", "properties": original}}
    original["items"]["items"]["properties"]["numbers"] = {
        "type": "array", "items": {"type": "number"},
    }
    for rule in schema["business_validation"]["rules"]:
        rule["collection"] = "/a~1b~0/items"
    schema["business_validation"]["rules"][0]["quantity"] = "/numbers/0"
    schema["business_validation"]["rules"][1]["target"] = "/a~1b~0/subtotal"
    assert validate_business_validation_schema(schema) == []


def test_normalization_and_portable_cli_keep_rules_and_report_bad_bindings(tmp_path: Path) -> None:
    directory = tmp_path / "schemas"
    directory.mkdir()
    schema = invoice_review_schema()
    path = directory / "invoice.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    config = TempConfig(tmp_path / "unused.sqlite3", {"schema": {"directories": [str(directory)]}})
    normalized = require_present(SchemaService(config).normalize_schema("invoice.json"))
    assert normalized["business_validation"] == schema["business_validation"]
    assert not validate_portable_file(path, kind="review-schema").errors
    schema["business_validation"]["rules"][1]["target"] = "/missing"
    path.write_text(json.dumps(schema), encoding="utf-8")
    result = validate_portable_file(path, kind="review-schema")
    assert any("business_validation.rules.1.target" in error.path for error in result.errors)


def test_versioned_rules_hashes_and_import_export_are_immutable(tmp_path: Path) -> None:
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    with connect(config) as conn:
        service = ReviewSchemaVersionService(conn)
        schema = invoice_review_schema()
        template = service.create_template(
            schema_key="invoice", name="Invoice", initial_schema=schema, user="admin",
        )["template"]
        first = service.publish(template["id"], expected_revision=1, user="admin")
        first_id = first["version"]["id"]
        for format in ("json", "yaml"):
            exported = service.export_version(first_id, format=format)
            assert service.import_document(exported) == schema
            assert service.import_document(service.export_draft(template["id"], format=format)) == schema
        schema["business_validation"]["rules"][0]["tolerance"] = "0.05"
        saved = service.save_draft(template["id"], expected_revision=2, schema=schema, user="admin")
        second = service.publish(template["id"], expected_revision=saved["revision"], user="admin")
        assert first["version"]["content_hash"] != second["version"]["content_hash"]
        assert service.load_version(first_id)["schema"]["business_validation"]["rules"][0].get("tolerance") is None
        assert service.load_version(second["version"]["id"])["schema"] == schema
        schema["business_validation"]["rules"][0]["validator"] = "missing:v1"
        saved = service.save_draft(template["id"], expected_revision=4, schema=schema, user="admin")
        with pytest.raises(ReviewSchemaValidationError):
            service.publish(template["id"], expected_revision=saved["revision"], user="admin")
    verify_business_validation_compatibility(config)


def test_unavailable_published_validator_rejected_by_load_and_startup(tmp_path: Path) -> None:
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    with connect(config) as conn:
        service = ReviewSchemaVersionService(conn)
        schema = invoice_review_schema()
        schema["business_validation"]["rules"][0]["validator"] = "future:v99"
        template = service.create_template(schema_key="old", name="Old", user=None)["template"]
        # Simulate a database from another deployment version with a retired plugin.
        version = service.versions.create(
            template_id=template["id"], version_number=1, format_version=1,
            schema_json=json.dumps(schema), content_hash=content_hash(schema),
            validation_summary_json="{}", user=None,
        )
        conn.commit()
        with pytest.raises(RuntimeError, match="unsupported or invalid"):
            service.load_version(version["id"])
    with pytest.raises(StartupReadinessError, match="unsupported or invalid"):
        verify_business_validation_compatibility(config)


@pytest.mark.parametrize("raw_json", [False, True])
def test_pipeline_dependencies_validate_pinned_rule_versions(raw_json: bool) -> None:
    schema = invoice_review_schema()
    schema["business_validation"]["rules"][0]["validator"] = "SYNTHETIC_DO_NOT_ECHO"
    dependency = {"id": "form-v1", **(
        {"schema_json": json.dumps(schema)} if raw_json else {"schema": schema}
    )}
    definition = {"tasks": {"review": {
        "class": "ReviewGateTask", "params": {"schema_version_id": "form-v1"},
    }}}
    findings = ValidationFacade._validate_schema_dependencies(definition, {"review": dependency})
    assert any(finding["code"] == "review-gate-business-rules-invalid" for finding in findings)
    assert "SYNTHETIC_DO_NOT_ECHO" not in json.dumps(findings)


def test_facade_reports_qualified_paths_without_changing_defaults() -> None:
    schema = invoice_review_schema()
    schema["business_validation"]["rules"][1]["target"] = "/missing"
    result = ValidationFacade().validate_review_schema(schema, source=ValidationSource("portable_review_schema"))
    assert not result["valid"]
    assert result["findings"][0]["path"].endswith("business_validation.rules.1.target")
