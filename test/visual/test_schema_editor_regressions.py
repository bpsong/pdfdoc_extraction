"""Source-level regression checks for the production schema editor."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_schema_editor_unifies_validation_and_unsaved_change_guards() -> None:
    source = (ROOT / "web/static/js/schema_editor.js").read_text(encoding="utf-8")

    assert "function collectClientFindings()" in source
    assert "function renderValidationSummary()" in source
    assert "function focusFinding(path)" in source
    assert "function pathsMatch(controlPath, findingPath)" in source
    assert "Invalid regular expression" not in source
    assert "Min length cannot be greater than max length." in source
    assert "Field key cannot be empty." in source
    assert "function confirmDiscardChanges()" in source
    assert "button.dataset.schemaName !== currentName && confirmDiscardChanges()" in source
    assert 'if (!confirmDiscardChanges()) {' in source
    assert "Object.keys(found.container).forEach" in source
    assert "dirty = true;" in source


def test_schema_editor_has_accessible_guidance_outline_and_responsive_rules() -> None:
    template = (ROOT / "web/templates/schema_editor.html").read_text(encoding="utf-8")
    styles = (ROOT / "web/static/css/app.css").read_text(encoding="utf-8")

    assert 'id="schema-action-guidance"' in template
    assert 'id="schema-field-outline"' in template
    assert 'role="status" aria-live="polite"' in template
    assert ".schema-field-outline" in styles
    assert ".schema-field-error" in styles
    assert ".schema-finding-link" in styles
    assert "grid-template-columns: minmax(14rem, 0.7fr) minmax(24rem, 1.3fr);" in styles
    assert "overflow: hidden;" in styles


def test_schema_editor_pattern_helper_and_visible_summary_are_wired() -> None:
    source = (ROOT / "web/static/js/schema_editor.js").read_text(encoding="utf-8")
    template = (ROOT / "web/templates/schema_editor.html").read_text(encoding="utf-8")
    styles = (ROOT / "web/static/css/app.css").read_text(encoding="utf-8")

    assert "function patternTester(path, prop, value)" in source
    assert 'window.DocFlow.apiPost("/api/schemas/pattern-test"' in source
    assert 'data-test-pattern="${escapeHtml(key)}"' in source
    assert "Example matches this pattern." in source
    assert "Example does not match this pattern." in source
    assert "function displayFindingPath(path)" in source
    assert source.count("patternExamples.clear();") == 2
    assert source.count("patternResults.clear();") == 2
    assert template.index('id="schema-validation-results"') < template.index('id="schema-yaml-preview"')
    assert ".schema-pattern-tester" in styles
    assert ".schema-pattern-result-success" in styles
    assert ".schema-validation-results:empty" in styles
