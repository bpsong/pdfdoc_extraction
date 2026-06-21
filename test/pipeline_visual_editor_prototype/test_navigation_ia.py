"""Regression checks for pipeline editor navigation ownership."""

from pathlib import Path


PROTOTYPE_ROOT = (
    Path(__file__).resolve().parents[2] / "pipeline_visual_editor_prototype"
)
MAIN_SOURCE = PROTOTYPE_ROOT / "src" / "main.jsx"


def test_task_inspector_only_exposes_task_scoped_tabs() -> None:
    """The selected-task inspector must not contain whole-pipeline tabs."""
    source = MAIN_SOURCE.read_text(encoding="utf-8")

    assert 'const tabs = [["properties", "Properties"], ["issues"' in source
    assert 'role="tablist" aria-label="Selected task"' in source
    assert 'activeTab === "yaml"' not in source
    assert 'activeTab === "diff"' not in source
    assert 'activeTab === "validate"' not in source


def test_pipeline_views_have_explicit_global_ownership() -> None:
    """Validation, YAML, and diff belong to the pipeline workspace."""
    source = MAIN_SOURCE.read_text(encoding="utf-8")

    assert 'aria-label="Pipeline tools"' in source
    assert 'role="dialog" aria-modal="true"' in source
    assert "Validate pipeline" in source
    assert "Pipeline YAML" in source
    assert "Review changes" in source
    assert "Whole pipeline" in source


def test_task_issues_are_filtered_to_the_selected_task() -> None:
    """Task issue counts must exclude unrelated pipeline findings."""
    source = MAIN_SOURCE.read_text(encoding="utf-8")

    assert 'item.path.startsWith(`tasks.${step.key}`)' in source
    assert 'item.path.startsWith(`steps.${index}.`)' in source
