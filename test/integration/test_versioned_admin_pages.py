"""Route and DOM-contract tests for versioned admin workspaces."""

from test.integration.test_new_ui_routes import authenticate, build_client


def test_admin_pages_render_versioned_workspace_contracts(monkeypatch):
    client = build_client(monkeypatch, username="admin")
    authenticate(client)

    schemas = client.get("/app/schemas")
    pipelines = client.get("/app/admin/pipeline")

    assert schemas.status_code == 200
    assert 'data-versioned="true"' in schemas.text
    assert 'id="schema-draft-revision"' in schemas.text
    assert 'id="schema-version-history"' in schemas.text
    assert 'versioned_admin_view_models.js' in schemas.text
    assert pipelines.status_code == 200
    assert 'id="pipeline-template-select"' in pipelines.text
    assert 'id="pipeline-binding-version"' in pipelines.text
    assert 'id="pipeline-draft-revision"' in pipelines.text
    assert 'id="pipeline-template-dialog"' in pipelines.text
    assert 'id="pipeline-template-dialog-key"' in pipelines.text
    assert 'versioned_admin_view_models.js' in pipelines.text


def test_operator_is_redirected_from_versioned_admin_pages(monkeypatch):
    client = build_client(monkeypatch, username="operator")
    authenticate(client)

    assert client.get("/app/schemas").status_code == 403
    assert client.get("/app/admin/pipeline").status_code == 403


def test_versioned_javascript_uses_exact_endpoints_not_legacy_mutations():
    schema_source = open(
        "web/static/js/schema_editor.js", encoding="utf-8"
    ).read()
    pipeline_source = open(
        "web/static/js/pipeline_config.js", encoding="utf-8"
    ).read()
    review_source = open(
        "web/static/js/human_review.js", encoding="utf-8"
    ).read()

    assert "/api/admin/review-schemas" in schema_source
    assert 'apiPut("/api/schemas' not in schema_source
    assert "/api/admin/pipeline-templates" in pipeline_source
    assert 'apiPut("/api/admin/pipeline/draft' not in pipeline_source
    assert "schema_version_id" in pipeline_source
    assert "schema_file" not in pipeline_source
    assert "window.prompt" not in pipeline_source
    assert 'data-param-type="secret-reference"' in pipeline_source
    assert "value.$secret" in pipeline_source
    assert "function scalarTextValue" in review_source
    assert "input.value = scalarTextValue(value)" in review_source
