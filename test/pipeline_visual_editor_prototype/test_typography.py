"""Regression checks for the visual pipeline editor typography system."""

from pathlib import Path


PROTOTYPE_ROOT = (
    Path(__file__).resolve().parents[2] / "pipeline_visual_editor_prototype"
)
MAIN_SOURCE = PROTOTYPE_ROOT / "src" / "main.jsx"
STYLE_SOURCE = PROTOTYPE_ROOT / "src" / "styles.css"


def test_editor_uses_production_system_font_stack() -> None:
    """The prototype should inherit production's portable system sans stack."""
    styles = STYLE_SOURCE.read_text(encoding="utf-8")

    assert "font-family: ui-sans-serif, system-ui, sans-serif" in styles
    assert "font-family: Inter, ui-sans-serif" not in styles


def test_form_controls_share_a_readable_type_scale() -> None:
    """Labels and controls should use the approved normalized sizes."""
    styles = STYLE_SOURCE.read_text(encoding="utf-8")

    assert ".btn:not(.btn-xs),\n.input,\n.select,\n.textarea" in styles
    assert "font-size: 0.875rem;" in styles
    assert ".label-text" in styles
    assert "font-size: 0.8125rem;" in styles


def test_meaningful_interface_text_is_not_below_twelve_pixels() -> None:
    """Task metadata and helper text must avoid the former 11px treatment."""
    source = MAIN_SOURCE.read_text(encoding="utf-8")

    assert "text-[11px]" not in source
    assert 'text-lg font-bold">Visual Pipeline Builder' in source
    assert 'text-base font-semibold">Task Palette' in source


def test_yaml_editor_uses_the_approved_code_size() -> None:
    """YAML and diff content should remain compact without becoming tiny."""
    styles = STYLE_SOURCE.read_text(encoding="utf-8")

    yaml_rule = styles.split("\n.yaml-box {", maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "font-size: 0.8125rem;" in yaml_rule
    assert "line-height: 1.55;" in yaml_rule
