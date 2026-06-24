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
