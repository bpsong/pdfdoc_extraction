"""Regression checks for production UI page-load optimizations."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_failure_notifications_are_cached_between_page_navigations() -> None:
    """Avoid repeating the shared notifications query on every app page."""

    app_source = (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")
    processing_source = (
        ROOT / "web/static/js/processing_overview.js"
    ).read_text(encoding="utf-8")
    base_template = (ROOT / "web/templates/app_base.html").read_text(encoding="utf-8")

    assert 'FAILURE_NOTIFICATION_CACHE_KEY = "docflow.failureNotifications"' in app_source
    assert "FAILURE_NOTIFICATION_CACHE_TTL_MS = 60_000" in app_source
    assert "Date.now() - cached.cachedAt < FAILURE_NOTIFICATION_CACHE_TTL_MS" in app_source
    assert "writeFailureNotificationCache(count)" in app_source
    assert "refreshFailureNotifications({ force: true })" in processing_source
    assert "app.js?v=ui-performance-notification-cache" in base_template


def test_admin_dashboard_renders_independent_requests_as_they_complete() -> None:
    """Keep the faster admin panel from waiting for the slower summary."""

    source = (ROOT / "web/static/js/admin.js").read_text(encoding="utf-8")
    template = (ROOT / "web/templates/admin_dashboard.html").read_text(
        encoding="utf-8"
    )

    assert "async function loadSummary()" in source
    assert "async function loadSettings()" in source
    assert "Promise.allSettled([" in source
    assert "loadSummary()," in source
    assert "loadSettings()," in source
    assert "admin.js?v=ui-performance-independent-panels" in template


def test_named_schema_route_resolves_to_versioned_template_identity() -> None:
    """Resolve a stable route key before loading the template-scoped draft."""

    source = (ROOT / "web/static/js/schema_editor.js").read_text(encoding="utf-8")
    template = (ROOT / "web/templates/schema_editor.html").read_text(
        encoding="utf-8"
    )

    assert 'window.DocFlow.apiGet("/api/admin/review-schemas?include_archived=true")' in source
    assert "schemas.find((schema) => schema.schema_key === currentName)" in source
    assert "await loadSchema(selected.id)" in source
    assert "rememberSchemaName(currentName)" in source
    assert "function initialSchemaName()" in source
    assert "schemaStem(rememberedName) === schemaStem(routeName)" in source
    assert "/api/admin/review-schemas/${encodeURIComponent(templateId)}" in source
    assert "schema_editor.js?v=ui-clarity-1" in template
