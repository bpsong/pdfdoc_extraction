"""Regression checks for production pipeline property forms."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_SOURCE = PROJECT_ROOT / "web" / "static" / "js" / "pipeline_config.js"


TASK_PARAMETERS: dict[str, set[str]] = {
    "LlamaCloudSplitTask": {"enabled", "categories", "api_key", "configuration_id", "project_id", "organization_id", "allow_uncategorized", "fail_on_confidence_levels", "fail_on_unknown_category", "allowed_categories", "poll_interval_seconds", "timeout_seconds", "split_dir"},
    "ExtractPdfTask": {"api_key", "configuration_id", "tier", "parse_tier", "extraction_target", "cite_sources", "confidence_scores", "project_id", "organization_id", "poll_interval_seconds", "timeout_seconds", "fields", "description", "is_table", "item_fields"},
    "ReviewGateTask": {"confidence_threshold", "per_document_type_thresholds", "field_threshold_overrides", "split_confidence_levels_requiring_review", "require_review_when_missing_confidence", "require_review_for_missing_required_fields", "always_review", "schema_file", "queue_name", "review_scope", "allow_operator_to_edit_high_confidence_fields", "resume_policy"},
    "StoreMetadataAsCsv": {"data_dir", "filename", "storage", "extraction"},
    "StoreMetadataAsJson": {"data_dir", "filename"},
    "StoreFileToLocaldrive": {"files_dir", "filename"},
    "UpdateReferenceTask": {"reference_file", "update_field", "write_value", "backup", "csv_match", "number"},
    "ArchivePdfTask": {"archive_dir"},
    "AssignNanoidTask": {"length"},
}


def test_production_editor_covers_every_user_configurable_task_parameter() -> None:
    source = PRODUCTION_SOURCE.read_text(encoding="utf-8")

    for class_name, parameters in TASK_PARAMETERS.items():
        assert class_name in source, class_name
        for parameter in parameters:
            assert parameter in source, f"{class_name}.{parameter}"


def test_production_editor_hides_runtime_housekeeping_controls() -> None:
    source = PRODUCTION_SOURCE.read_text(encoding="utf-8")

    assert 'kind === "housekeeping"' not in source
    assert 'directoryControl("Processing directory"' not in source


def test_production_editor_has_prototype_interaction_builders() -> None:
    source = PRODUCTION_SOURCE.read_text(encoding="utf-8")

    for marker in (
        "insert-filename-token",
        "add-rule-clause",
        "confidence-percent",
        "save-row-schema",
        "apply-advanced-params",
        "duplicate-task",
        "confirm-remove-task",
    ):
        assert marker in source


def test_production_editor_uses_runtime_defaults_and_supported_provider_values() -> None:
    source = PRODUCTION_SOURCE.read_text(encoding="utf-8")

    assert 'allow_uncategorized: "include"' in source
    assert 'LlamaCloudSplitTask: { enabled: true, api_key: "", configuration_id:' not in source
    assert 'ExtractPdfTask: { api_key: "", configuration_id:' not in source
    assert "AssignNanoidTask: { length: 10 }" in source
    assert "ReviewGateTask: { confidence_threshold: 0.8" in source
    assert 'const supportedTiers = ["agentic", "cost_effective"]' in source
    assert '{ value: "premium"' not in source
    assert '{ value: "balanced"' not in source


def test_production_editor_separates_provider_modes_and_hides_operational_controls() -> None:
    source = PRODUCTION_SOURCE.read_text(encoding="utf-8")

    assert source.count('data-param-action="provider-mode"') == 2
    assert source.count('detailsSection("Advanced provider settings"') == 2
    assert 'textControl("Task status key' not in source
    assert 'selectControl("After review"' not in source
    assert "Schema errors only" not in source
    assert "Document split result" not in source
