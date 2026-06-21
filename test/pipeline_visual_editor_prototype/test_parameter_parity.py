"""Production parameter coverage tests for the visual pipeline editor."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EDITOR_SOURCE = (
    PROJECT_ROOT / "pipeline_visual_editor_prototype" / "src" / "main.jsx"
)


TASK_PARAMETERS: dict[str, set[str]] = {
    "LlamaCloudSplitTask": {
        "enabled",
        "categories",
        "api_key",
        "configuration_id",
        "project_id",
        "organization_id",
        "allow_uncategorized",
        "fail_on_confidence_levels",
        "fail_on_unknown_category",
        "allowed_categories",
        "poll_interval_seconds",
        "timeout_seconds",
        "split_dir",
    },
    "ExtractPdfTask": {
        "api_key",
        "configuration_id",
        "tier",
        "parse_tier",
        "extraction_target",
        "cite_sources",
        "confidence_scores",
        "project_id",
        "organization_id",
        "poll_interval_seconds",
        "timeout_seconds",
        "fields",
        "description",
        "is_table",
        "item_fields",
    },
    "ReviewGateTask": {
        "confidence_threshold",
        "per_document_type_thresholds",
        "field_threshold_overrides",
        "split_confidence_levels_requiring_review",
        "require_review_when_missing_confidence",
        "require_review_for_missing_required_fields",
        "always_review",
        "schema_file",
        "queue_name",
        "review_scope",
        "allow_operator_to_edit_high_confidence_fields",
        "resume_policy",
    },
    "StoreMetadataAsCsv": {
        "data_dir",
        "filename",
        "storage",
        "extraction",
        "task_slug",
    },
    "StoreMetadataAsJson": {"data_dir", "filename"},
    "StoreFileToLocaldrive": {"files_dir", "filename"},
    "UpdateReferenceTask": {
        "reference_file",
        "update_field",
        "write_value",
        "backup",
        "task_slug",
        "csv_match",
        "number",
    },
    "ArchivePdfTask": {"archive_dir"},
    "AssignNanoidTask": {"length"},
}

RUNTIME_MANAGED_TASKS = {"CleanupTask"}


def test_every_builtin_task_has_a_palette_definition() -> None:
    """Ensure every user-configurable built-in can be added from the palette."""
    source = EDITOR_SOURCE.read_text(encoding="utf-8")

    for class_name in TASK_PARAMETERS:
        assert f'class: "{class_name}"' in source, class_name


def test_runtime_managed_tasks_are_not_exposed_in_the_palette() -> None:
    """Keep automatic lifecycle tasks out of the user-authored pipeline UI."""
    source = EDITOR_SOURCE.read_text(encoding="utf-8")

    for class_name in RUNTIME_MANAGED_TASKS:
        assert f'class: "{class_name}"' not in source, class_name


def test_every_supported_parameter_has_editor_coverage() -> None:
    """Ensure production YAML parameter names remain represented in the editor."""
    source = EDITOR_SOURCE.read_text(encoding="utf-8")

    for class_name, parameters in TASK_PARAMETERS.items():
        for parameter in parameters:
            assert parameter in source, f"{class_name}.{parameter}"


def test_review_gate_options_match_production_validation() -> None:
    """Prevent unsupported resume modes and mandatory-schema regressions."""
    source = EDITOR_SOURCE.read_text(encoding="utf-8")

    assert "restart_pipeline" not in source
    assert "Review gate needs a schema file" not in source


def test_reference_comparison_preserves_three_state_behavior() -> None:
    """Require Auto, Text, and Numeric choices for clause comparisons."""
    source = EDITOR_SOURCE.read_text(encoding="utf-8")

    for label in ("Auto-detect", "Text comparison", "Numeric comparison"):
        assert label in source
