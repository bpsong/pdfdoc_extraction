"""Unit tests for versioned administration read models."""

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.versioned_admin_service import VersionedAdminService
from test.helpers_sqlite import TempConfig


def test_admin_read_models_include_revisions_usage_and_redact_secrets(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    with connect(config) as conn:
        schemas = ReviewSchemaVersionService(conn)
        schema = schemas.create_template(
            schema_key="invoice",
            name="Invoice",
            initial_schema={
                "fields": {"supplier": {"type": "string", "label": "Supplier"}}
            },
            user="admin",
        )
        schema_published = schemas.publish(
            schema["template"]["id"], expected_revision=1, user="admin"
        )
        schemas.update_template(
            schema["template"]["id"], status="active", user="admin"
        )
        pipelines = PipelineTemplateService(
            conn, configured_secret_aliases={"extract-api"}
        )
        pipeline = pipelines.create_template(
            template_key="invoice",
            name="Invoice",
            initial_definition={
                "schema_version": 1,
                "pipeline": ["extract", "review"],
                "tasks": {
                    "extract": {
                        "module": "standard_step.extraction.extract_pdf",
                        "class": "ExtractPdfTask",
                        "params": {
                            "api_key": {"$secret": "extract-api"},
                            "fields": {
                                "supplier": {"alias": "Supplier", "type": "str"}
                            },
                        },
                    },
                    "review": {
                        "module": "standard_step.review.review_gate",
                        "class": "ReviewGateTask",
                        "params": {
                            "schema_version_id": schema_published["version"]["id"]
                        },
                    },
                },
            },
            user="admin",
        )
        published = pipelines.publish(
            pipeline["template"]["id"], expected_revision=1, user="admin"
        )

        admin = VersionedAdminService(
            conn, configured_secret_aliases={"extract-api"}
        )
        schema_summary = admin.list_schema_templates()[0]
        workspace = admin.get_pipeline_template(pipeline["template"]["id"])
        version = admin.get_pipeline_version(
            pipeline["template"]["id"], published["version"]["id"]
        )

        assert schema_summary["draft_revision"] == 2
        assert schema_summary["usage_count"] == 1
        assert workspace["draft"]["definition"]["tasks"]["extract"]["params"][
            "api_key"
        ] == {"$secret": "extract-api"}
        assert "runtime-secret" not in str(workspace)
        assert version["schema_dependency_summaries"][0]["schema_key"] == "invoice"


def test_pipeline_group_identity_uses_exact_version_not_only_hash():
    from modules.services.processing_state_service import _pipeline_groups

    snapshot = {"version": 1, "content_hash": "same", "steps": []}
    groups = _pipeline_groups(
        [
            {
                "batch": {"id": "one"},
                "documents": [],
                "pipeline": {"pipeline_version_id": "v1"},
                "pipeline_snapshot": snapshot,
            },
            {
                "batch": {"id": "two"},
                "documents": [],
                "pipeline": {"pipeline_version_id": "v2"},
                "pipeline_snapshot": snapshot,
            },
        ]
    )

    assert {group["pipeline_version_id"] for group in groups} == {"v1", "v2"}
