"""Capability versioning prevents older releases silently skipping business rules."""

from contextlib import closing
import json

import pytest

from modules.db.connection import connect
from modules.services.business_validation_schema import require_business_rule_capability
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.startup_migration_service import initialize_database
from modules.services.startup_service import verify_business_validation_compatibility
from modules.services.validation_facade import ValidationFacade
from modules.services.versioned_config_contracts import content_hash
from test.helpers_business_validation import invoice_review_schema
from test.helpers_sqlite import TempConfig


def test_legacy_rule_form_is_retained_but_explicitly_republished_as_format_two(tmp_path):
    config = TempConfig(tmp_path / "state.sqlite3")
    initialize_database(config)
    schema = invoice_review_schema()
    with closing(connect(config)) as conn:
        service = ReviewSchemaVersionService(conn)
        template = service.create_template(schema_key="legacy", name="Legacy", initial_schema=schema, user="admin")["template"]
        old = service.versions.create(template_id=template["id"], version_number=1, format_version=1,
            schema_json=json.dumps(schema), content_hash=content_hash(schema), validation_summary_json="{}", user="admin")
        service.drafts.reset_to_version(template_id=template["id"], version_id=old["id"],
            schema_json=old["schema_json"], content_hash=old["content_hash"], user="admin")
        conn.commit()
        # Admin can inspect the old record; execution cannot enable rules implicitly.
        assert service.load_version(old["id"])["format_version"] == 1
        with pytest.raises(ValueError, match="Republish"):
            require_business_rule_capability(schema, 1)
        new = service.publish(template["id"], expected_revision=2, user="admin")["version"]
        assert new["format_version"] == 2
        assert new["content_hash"] == old["content_hash"]
        assert new["id"] != old["id"]
        assert service.load_version(old["id"])["format_version"] == 1
        exported = service.export_version(new["id"], format="json")
        assert json.loads(exported)["format_version"] == 2
        assert service.import_document(exported) == schema
        # Former loaders required format 1 and reject this mandatory capability.
        assert new["format_version"] != 1
    verify_business_validation_compatibility(config)


@pytest.mark.parametrize("format_version,valid", [(1, False), (2, True), (3, False), (True, False)])
def test_pipeline_dependency_requires_rule_capability(format_version, valid):
    definition = {"tasks": {"review": {"class": "ReviewGateTask", "params": {"schema_version_id": "v"}}}}
    findings = ValidationFacade._validate_schema_dependencies(definition, {"review": {
        "id": "v", "schema": invoice_review_schema(), "format_version": format_version,
    }})
    assert (not findings) is valid


def test_no_rules_forms_keep_legacy_format(tmp_path):
    config = TempConfig(tmp_path / "state.sqlite3")
    initialize_database(config)
    with closing(connect(config)) as conn:
        service = ReviewSchemaVersionService(conn)
        template = service.create_template(schema_key="plain", name="Plain", initial_schema={"fields": {}}, user="admin")["template"]
        version = service.publish(template["id"], expected_revision=1, user="admin")["version"]
        assert version["format_version"] == 1
        require_business_rule_capability(version["schema"], 1)
