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
    assert "button.dataset.schemaId !== currentId && confirmDiscardChanges()" in source
    assert 'if (!confirmDiscardChanges()) {' in source
    assert "Object.keys(found.container).forEach" in source
    assert "dirty = true;" in source


def test_schema_editor_creates_review_forms_with_an_accessible_modal() -> None:
    source = (ROOT / "web/static/js/schema_editor.js").read_text(encoding="utf-8")
    template = (ROOT / "web/templates/schema_editor.html").read_text(encoding="utf-8")

    assert 'id="schema-create-modal"' in template
    assert 'role="dialog" aria-modal="true" aria-labelledby="schema-create-title"' in template
    assert 'id="schema-create-form"' in template
    assert 'id="schema-create-key"' in template
    assert 'id="schema-create-name"' in template
    assert 'createModal.classList.remove("hidden");' in source
    assert 'createModal.classList.add("flex");' in source
    assert "function closeCreateModal()" in source
    assert 'createForm.addEventListener("submit"' in source
    assert 'window.DocFlow.apiPost("/api/admin/review-schemas"' in source
    assert "window.prompt" not in source


def test_schema_editor_has_accessible_guidance_outline_and_responsive_rules() -> None:
    template = (ROOT / "web/templates/schema_editor.html").read_text(encoding="utf-8")
    styles = (ROOT / "web/static/css/app.css").read_text(encoding="utf-8")

    assert 'id="schema-action-guidance"' in template
    assert 'id="schema-field-outline"' in template
    assert 'role="status" aria-live="polite"' in template
    assert 'id="schema-field-status"' in template
    assert ".schema-field-outline" in styles
    assert ".schema-field-actions" in styles
    assert ".schema-delete-field" in styles
    assert ".schema-field-error" in styles
    assert ".schema-finding-link" in styles
    assert "grid-template-columns: minmax(14rem, 0.7fr) minmax(24rem, 1.3fr);" in styles
    assert "overflow: hidden;" in styles


def test_schema_and_pipeline_editors_share_admin_panel_structure() -> None:
    schema_template = (ROOT / "web/templates/schema_editor.html").read_text(encoding="utf-8")
    pipeline_template = (ROOT / "web/templates/pipeline_config.html").read_text(encoding="utf-8")
    styles = (ROOT / "web/static/css/app.css").read_text(encoding="utf-8")

    assert schema_template.count('class="admin-panel ') == 3
    assert schema_template.count('class="admin-panel-header"') == 3
    assert "schema-panel-header" not in schema_template
    assert pipeline_template.count('class="admin-panel ') == 9
    assert pipeline_template.count('class="admin-panel-header"') == 7
    assert 'class="card ' not in pipeline_template
    assert 'class="panel-header"' not in pipeline_template
    assert schema_template.count("admin-panel-title") == 3
    assert pipeline_template.count("admin-panel-title") == 7
    assert ".admin-panel" in styles
    assert ".admin-panel-header" in styles
    assert ".admin-panel-heading" in styles
    assert ".admin-panel-title" in styles
    assert ".admin-panel-subtitle" in styles
    assert ".admin-panel-actions" in styles
    assert ".schema-panel-header" not in styles


def test_pipeline_template_and_publish_guide_use_distinct_grid_rows() -> None:
    """Prevent the publish guide from covering template metadata controls."""
    template = (ROOT / "web/templates/pipeline_config.html").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "web/static/css/app.css").read_text(encoding="utf-8")

    assert template.count('class="admin-panel pipeline-template-panel"') == 1
    assert template.count('class="admin-panel pipeline-guide-panel"') == 1
    assert ".pipeline-template-panel" in styles
    assert '"template template template"' in styles
    assert '"guide guide guide"' in styles
    assert '"template template"' in styles
    assert '"guide guide"' in styles
    assert '"template"' in styles
    assert '"guide"' in styles


def test_pipeline_activation_is_distinct_from_draft_reset() -> None:
    """Keep upload availability separate from restoring a published draft."""
    template = (ROOT / "web/templates/pipeline_config.html").read_text(
        encoding="utf-8"
    )
    source = (ROOT / "web/static/js/pipeline_config.js").read_text(encoding="utf-8")

    assert 'id="pipeline-template-activate"' in template
    assert ">Activate for uploads</button>" in template
    assert "Availability status" in template
    assert "Reset draft to published version" in template
    assert "This does not change pipeline availability." in template
    assert "function syncTemplateLifecycleControls()" in source
    assert 'templateMetadataPayload({ status: "active" })' in source
    assert "Pipeline activated. It is now available on Upload & Process." in source
    assert "does not change pipeline availability" in source


def test_pipeline_creation_uses_an_accessible_in_page_modal() -> None:
    template = (ROOT / "web/templates/pipeline_config.html").read_text(encoding="utf-8")
    source = (ROOT / "web/static/js/pipeline_config.js").read_text(encoding="utf-8")

    assert 'id="pipeline-template-dialog"' in template
    assert 'role="dialog" aria-modal="true"' in template
    assert 'id="pipeline-template-form"' in template
    assert "function closeTemplateDialog()" in source
    assert 'templateDialog.classList.remove("hidden");' in source
    assert 'templateDialog.classList.add("flex");' in source
    assert "templateDialog.showModal()" not in source


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
    assert source.count("patternExamples.clear();") == 1
    assert source.count("patternResults.clear();") == 1
    assert template.index('id="schema-validation-results"') < template.index('id="schema-yaml-preview"')
    assert ".schema-pattern-tester" in styles
    assert ".schema-pattern-result-success" in styles
    assert ".schema-validation-results:empty" in styles


def test_schema_editor_has_safe_delete_and_sibling_reordering() -> None:
    source = (ROOT / "web/static/js/schema_editor.js").read_text(encoding="utf-8")

    assert "function moveField(pathText, direction)" in source
    assert 'data-move-field="${escapeHtml(fullPath)}"' in source
    assert 'data-move-direction="up"' in source
    assert 'data-move-direction="down"' in source
    assert "movement.canMoveUp" in source
    assert "movement.canMoveDown" in source
    assert 'class="btn btn-outline btn-error btn-xs schema-delete-field"' in source
    assert 'Delete field "${fieldName}" from this schema draft?' in source
    assert "if (!confirmed)" in source
    assert "focusFieldAction(pathText, direction)" in source
    assert "announceFieldChange(`Moved ${fieldName} ${direction}.`)" in source
    assert "announceFieldChange(`Deleted ${fieldName} from the schema draft.`)" in source


def test_extraction_editor_explains_its_single_table_limit() -> None:
    source = (ROOT / "web/static/js/pipeline_config.js").read_text(encoding="utf-8")

    assert "tableKeys.length >= 1" in source
    assert 'option.value === "List[Any]" && tableBlocked' in source
    assert "Each extraction task supports one List of objects field." in source
    assert "The additional table option stays unavailable once one is configured." in source


def test_pipeline_text_parameters_update_while_typing() -> None:
    """Keep draft text edits available when the user saves without changing focus."""
    source = (ROOT / "web/static/js/pipeline_config.js").read_text(encoding="utf-8")

    assert 'workspace.addEventListener("input", (event) => {' in source
    assert (
        'textarea[data-param-path], input[data-param-path]:not([type]), '
        'input[type=\'text\'][data-param-path]'
    ) in source
    assert "updateParamControl(liveParamField);" in source


def test_pipeline_editor_distinguishes_live_and_draft_states() -> None:
    template = (ROOT / "web/templates/pipeline_config.html").read_text(
        encoding="utf-8"
    )
    source = (ROOT / "web/static/js/pipeline_config.js").read_text(encoding="utf-8")

    assert "Live pipeline" in template
    assert "Editing draft" in template
    assert "Read-only published version" in template
    assert "Publish to make changes live" in source
    assert "Each extraction task supports one List of objects field." in source
    assert "extraction-field-details" in source


def test_review_form_editor_warns_without_renaming_mismatched_names() -> None:
    template = (ROOT / "web/templates/schema_editor.html").read_text(encoding="utf-8")
    source = (ROOT / "web/static/js/schema_editor.js").read_text(encoding="utf-8")

    assert 'id="schema-identity-warning"' in template
    assert 'id="schema-field-search"' in template
    assert "They remain unchanged; confirm the intended form before publishing." in source
    assert "schema-field-details" in source
    assert "fieldSearchInput.addEventListener" in source


def test_pipeline_and_schema_editors_restore_focus_after_dom_replacement() -> None:
    pipeline_source = (ROOT / "web/static/js/pipeline_config.js").read_text(
        encoding="utf-8"
    )
    schema_source = (ROOT / "web/static/js/schema_editor.js").read_text(
        encoding="utf-8"
    )

    assert "function captureEditorFocus()" in pipeline_source
    assert "function renderEditorWithFocusRestore()" in pipeline_source
    assert "renderEditorWithFocusRestore();" in pipeline_source
    assert "field.dataset.fieldKey = newKey;" in pipeline_source
    assert "field.dataset.oldKey = newKey;" in pipeline_source
    assert "function captureFieldTreeFocus()" in schema_source
    assert "function renderFieldTreeWithFocusRestore()" in schema_source
    assert "renderFieldTreeWithFocusRestore();" in schema_source
    assert "active.dataset.fieldPath = renamedPath;" in schema_source
    assert "focus({ preventScroll: true })" in pipeline_source
    assert "focus({ preventScroll: true })" in schema_source
