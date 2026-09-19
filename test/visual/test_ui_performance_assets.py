"""Regression checks for production UI page-load optimizations."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_failure_notifications_are_cached_between_page_navigations() -> None:
    """Avoid repeating the shared notifications query on every app page."""

    app_source = (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")
    processing_source = (
        ROOT / "web/static/js/processing-overview/controller.js"
    ).read_text(encoding="utf-8")
    base_template = (ROOT / "web/templates/app_base.html").read_text(encoding="utf-8")

    assert 'FAILURE_NOTIFICATION_CACHE_KEY = "docflow.failureNotifications"' in app_source
    assert "FAILURE_NOTIFICATION_CACHE_TTL_MS = 60_000" in app_source
    assert "Date.now() - cached.cachedAt < FAILURE_NOTIFICATION_CACHE_TTL_MS" in app_source
    assert "writeFailureNotificationCache(count)" in app_source
    assert "refreshFailureNotifications({ force: true })" in processing_source
    assert "app.js?v=review-status-vocabulary" in base_template


def test_admin_dashboard_renders_independent_requests_as_they_complete() -> None:
    """Keep the faster admin panel from waiting for the slower summary."""

    source = (ROOT / "web/static/js/admin-dashboard/controller.js").read_text(encoding="utf-8")
    template = (ROOT / "web/templates/admin_dashboard.html").read_text(
        encoding="utf-8"
    )

    assert "async function loadSummary()" in source
    assert "async function loadSettings()" in source
    assert "Promise.allSettled([" in source
    assert "loadSummary()," in source
    assert "loadSettings()," in source
    assert "admin-dashboard/index.js?v=controller-modularization-7a" in template


def test_named_schema_route_resolves_to_versioned_template_identity() -> None:
    """Resolve a stable route key before loading the template-scoped draft."""

    source = (ROOT / "web/static/js/schema-editor/controller.js").read_text(encoding="utf-8")
    template = (ROOT / "web/templates/schema_editor.html").read_text(
        encoding="utf-8"
    )

    assert "api.listTemplates()" in source
    assert "schemas.find((schema) => schema.schema_key === currentName)" in source
    assert "await loadSchema(selected.id)" in source
    assert "rememberSchemaName(currentName)" in source
    assert "function initialSchemaName()" in source
    assert "schemaStem(rememberedName) === schemaStem(routeName)" in source
    assert "api.getTemplate(templateId)" in source
    assert "schema-editor/index.js?v=controller-modularization-5d" in template


def test_processing_review_and_upload_feedback_surfaces_are_present() -> None:
    """Keep the operator feedback regions and upload progress contract visible."""

    base_template = (ROOT / "web/templates/app_base.html").read_text(encoding="utf-8")
    processing_template = (
        ROOT / "web/templates/processing_overview.html"
    ).read_text(encoding="utf-8")
    review_template = (ROOT / "web/templates/review_queue.html").read_text(
        encoding="utf-8"
    )
    upload_template = (ROOT / "web/templates/upload_process.html").read_text(
        encoding="utf-8"
    )
    processing_source = (
        ROOT / "web/static/js/processing-overview/controller.js"
    ).read_text(encoding="utf-8")
    review_source = (ROOT / "web/static/js/review-queue/controller.js").read_text(encoding="utf-8")
    review_view = (ROOT / "web/static/js/review-queue/view.js").read_text(encoding="utf-8")
    upload_source = (ROOT / "web/static/js/upload-process/controller.js").read_text(encoding="utf-8")
    upload_api = (ROOT / "web/static/js/upload-process/api.js").read_text(encoding="utf-8")
    upload_model = (ROOT / "web/static/js/upload-process/model.js").read_text(encoding="utf-8")
    extraction_source = (
        ROOT / "web/static/js/extraction-results/view.js"
    ).read_text(encoding="utf-8")
    human_review_source = (
        ROOT / "web/static/js/human-review/field-view.js"
    ).read_text(encoding="utf-8")

    assert 'id="app-announcement-region"' in base_template
    assert 'role="status"' in base_template
    assert 'id="processing-progress-region"' in processing_template
    assert 'id="processing-table-body"' in processing_template
    assert 'aria-busy="true"' in processing_template
    assert "announceProcessingChanges(states)" in processing_source
    assert 'id="review-queue-region"' in review_template
    assert "announceReviewChanges(state.items, nextItems)" in review_source
    assert "confidence ·" in review_view
    assert "confidence ·" in extraction_source
    assert "confidence ·" in human_review_source
    assert 'id="upload-progress-bar"' in upload_template
    assert 'role="status"' in upload_template
    assert 'xhr.open("POST", "/api/batches/upload")' in upload_api
    assert "xhr.upload.addEventListener(\"progress\"" in upload_api
    assert "function validateBatch(entries)" in upload_model
    assert "error.status === 429" in upload_source


def test_operator_help_retry_keyboard_and_table_polish_are_present() -> None:
    """Protect the low-risk operator affordances and scoped layout treatment."""

    app_source = (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")
    upload_source = (ROOT / "web/static/js/upload-process/controller.js").read_text(encoding="utf-8")
    upload_api = (ROOT / "web/static/js/upload-process/api.js").read_text(encoding="utf-8")
    review_source = (ROOT / "web/static/js/review-queue/controller.js").read_text(encoding="utf-8")
    processing_source = (
        ROOT / "web/static/js/processing-overview/controller.js"
    ).read_text(encoding="utf-8")
    upload_template = (ROOT / "web/templates/upload_process.html").read_text(encoding="utf-8")
    review_template = (ROOT / "web/templates/review_queue.html").read_text(encoding="utf-8")
    processing_template = (
        ROOT / "web/templates/processing_overview.html"
    ).read_text(encoding="utf-8")
    extraction_template = (
        ROOT / "web/templates/extraction_results.html"
    ).read_text(encoding="utf-8")
    css_source = (ROOT / "web/static/css/app.css").read_text(encoding="utf-8")

    assert "statusBadgeClass" in app_source
    assert "tableSkeletonRows" in app_source
    assert 'role="button"' in upload_template
    assert 'id="cancel-upload-button"' in upload_template
    assert 'dropZone.addEventListener("keydown"' in upload_source
    assert 'error.name = "AbortError"' in upload_api
    assert "data-review-retry" in review_source
    assert "data-processing-retry" in processing_source
    assert "app-filter-bar" in review_template
    assert "app-queue-table-region" in review_template
    assert "app-queue-table-region" in processing_template
    assert "table-zebra app-queue-table" in review_template
    assert "table-zebra app-queue-table" in processing_template
    assert "context-help" in upload_template
    assert "context-help" in extraction_template
    assert ".app-queue-table thead th" in css_source
    assert ".placeholder-row" in css_source
