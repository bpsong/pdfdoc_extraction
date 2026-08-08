"""Regression checks for intent-revealing admin labels."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_task_catalog_describes_its_configuration_scope() -> None:
    template = (ROOT / "web/templates/task_catalog.html").read_text(encoding="utf-8")
    source = (ROOT / "web/static/js/task_catalog.js").read_text(encoding="utf-8")

    assert "Usage reflects the running config.yaml, not versioned pipeline drafts." in template
    assert "Used in config.yaml" in template
    assert "Not in config.yaml" in source


def test_validation_results_name_the_checked_target() -> None:
    template = (ROOT / "web/templates/config_validation.html").read_text(encoding="utf-8")
    source = (ROOT / "web/static/js/config_validation.js").read_text(encoding="utf-8")

    assert "Selected target" in template
    assert "Check config.yaml" in template
    assert "Target: ${state.target}" in source
    assert "${state.target}: ${summary.errors > 0 ? \"blocked\" : \"ready\"}" in source


def test_reports_explain_batch_actions_and_review_state() -> None:
    template = (ROOT / "web/templates/reports.html").read_text(encoding="utf-8")
    source = (ROOT / "web/static/js/reports.js").read_text(encoding="utf-8")

    assert "Average processing time" in template
    assert "Open processing dashboard" in template
    assert "Workflow state" in template
    assert "Awaiting review" in source
    assert "Processing complete" in source
