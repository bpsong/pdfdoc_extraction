"""FastAPI application entry module.

Responsibilities:
- Provide an app factory to construct the FastAPI application.
- Configure and mount static and template directories (Jinja2).
- Configure CORS only when explicit allowed origins are provided.
- Define simple HTML routes: login, dashboard, and upload.
- Include API routes assembled via modules.api_router.build_router().
- Register graceful shutdown hook via ShutdownManager.
"""

from pathlib import Path
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import json
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from modules.api_router import build_router, get_dependencies
from modules.shutdown_manager import ShutdownManager
from modules.config_manager import ConfigManager
from modules.auth_utils import AuthUtils, AuthError, LoginRateLimitError
from modules.db.migrations import initialize_database


def _cors_allowed_origins(config: ConfigManager) -> list[str]:
    """Return explicitly configured CORS origins.

    Same-origin browser use does not need CORS, so the safe default is an
    empty list. A comma-separated string is accepted for simple env-driven
    configuration.
    """
    value = config.get("web.cors_allowed_origins", [])
    if isinstance(value, str):
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    if isinstance(value, list):
        return [str(origin).strip() for origin in value if str(origin).strip()]
    return []


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Sets up static and template directories, middleware, simple HTML routes,
    API router inclusion, and graceful shutdown integration.

    Args:
        None

    Returns:
        FastAPI: The configured FastAPI application instance.

    Notes:
        - The 'web/static' and 'web/templates' directories are created if missing.
        - CORS is disabled by default because the app serves its own browser UI.
          Configure web.cors_allowed_origins only for a separate trusted frontend.
        - API routes are composed via modules.api_router.build_router().
        - ShutdownManager is registered to handle application shutdown events.
    """
    app = FastAPI(title="PDF Processing Web Interface", version="1.0.0")
    logger = logging.getLogger("web.server")

    # Static and Templates
    static_dir = Path("web/static")
    templates_dir = Path("web/templates")
    static_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))

    try:
        config, _, _, _, _ = get_dependencies()
        allowed_origins = _cors_allowed_origins(config)
        if allowed_origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=allowed_origins,
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type"],
                allow_credentials=True,
            )
        if bool(config.get("database.run_migrations_on_startup", True)):
            initialize_database(config)
    except Exception as exc:
        logger.warning("Database initialization during web startup failed: %s", exc)

    # Helper: read/validate JWT from cookie; return username or None
    async def get_current_user(request: Request) -> Optional[str]:
        """Get the current authenticated user from the request cookie.
        
        Args:
            request: The FastAPI request object
            
        Returns:
            The username if authenticated, None otherwise
        """
        token = request.cookies.get("access_token")
        if not token:
            logger.debug("No access_token cookie found")
            return None

        try:
            # Get auth instance from dependencies
            _, auth, _, _, _ = get_dependencies()
            username = auth.get_current_user(token)
            logger.debug(f"Valid token for user: {username}")
            return username
        except AuthError as e:
            logger.info(f"Invalid token: {e}")
            return None

    async def get_current_active_user(request: Request) -> str:
        """Get the current user or redirect to login if not authenticated.

        Args:
            request: The FastAPI request object

        Returns:
            The username if authenticated

        Raises:
            HTTPException: Redirects to login if not authenticated

        HTTP Error Codes:
            - 200: User is authenticated, returns username
            - 307: Authentication required, redirects to login page
        """
        username = await get_current_user(request)
        if not username:
            logger.info("Authentication required, redirecting to login")
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                detail="Not authenticated",
                headers={"Location": "/login"},
            )
        return username

    def _as_string_list(value: Any) -> list[str]:
        """Normalize a config value into a list of non-empty strings."""

        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if str(item)]
        return []

    def _is_admin_user(username: str, config: Any) -> bool:
        """Return whether a username has admin access for app UI routes."""

        if not bool(config.get("ui.admin_enabled", True)):
            return False
        if not bool(config.get("auth.roles_enabled", True)):
            return True

        admin_users = set(_as_string_list(config.get("auth.default_admin_users", [])))
        admin_users.update(_as_string_list(config.get("ui.default_admin_users", [])))
        if admin_users:
            return username in admin_users

        configured_username = config.get("authentication.username")
        return bool(configured_username and username == str(configured_username))

    async def render_app_page(
        request: Request,
        template_name: str,
        *,
        page_title: str,
        page_subtitle: str = "",
        active_nav: str = "",
        admin_required: bool = False,
        **extra_context: Any,
    ) -> HTMLResponse:
        """Render an authenticated app page with role-aware shared context."""

        username = await get_current_active_user(request)
        config, _, _, _, _ = get_dependencies()
        is_admin = _is_admin_user(username, config)
        if admin_required and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required",
            )

        return templates.TemplateResponse(
            template_name,
            {
                "request": request,
                "is_authenticated": True,
                "username": username,
                "is_admin": is_admin,
                "user_role": "admin" if is_admin else "operator",
                "app_name": config.get("ui.app_name", "DocFlow AI"),
                "page_title": page_title,
                "page_subtitle": page_subtitle,
                "active_nav": active_nav,
                **extra_context,
            },
        )

    # --- Routes ---

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Redirect to the refactored app when logged in, otherwise to login."""
        username = await get_current_user(request)
        if username:
            return RedirectResponse(url="/app/upload", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        else:
            return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        """Serves the login page."""
        username = await get_current_user(request)
        if username:
            logger.info(f"/login GET: user already authenticated -> {username}, redirecting to /app/upload")
            return RedirectResponse(url="/app/upload", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        
        logger.info("/login GET: unauthenticated, rendering login page")
        response = templates.TemplateResponse(
            "login.html",
            {"request": request, "error": None, "is_authenticated": False}
        )
        # Prevent browser caching of login page
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    async def _extract_credentials(request: Request) -> tuple[str, str]:
        """Extract username and password from form or JSON payload."""

        content_type = request.headers.get("content-type", "").lower()
        body = await request.body()
        if not body:
            return "", ""

        if "application/x-www-form-urlencoded" in content_type:
            decoded = body.decode("utf-8", errors="replace")
            parsed = parse_qs(decoded, keep_blank_values=True)
            username = parsed.get("username", [""])[0]
            password = parsed.get("password", [""])[0]
            return username, password

        if "application/json" in content_type:
            try:
                payload = json.loads(body.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                return "", ""
            username = str(payload.get("username", ""))
            password = str(payload.get("password", ""))
            return username, password

        return "", ""

    def _client_identifier(request: Request) -> str:
        """Return a stable client identifier for login throttling."""

        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    @app.post("/login")
    async def login_post(request: Request):
        """Handles login form submission, verifies credentials, sets cookie, redirects.
        
        On successful authentication: sets HttpOnly cookie and redirects to the refactored app.
        On authentication failure: returns login page with error message and cache-control headers
        to prevent browser caching of error responses.
        """
        username, password = await _extract_credentials(request)
        if not username or not password:
            logger.warning("Login attempt with missing credentials")
            response = templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid username or password", "is_authenticated": False}
            )
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        logger.info(f"Login attempt for username: {username}")
        
        try:
            # Get auth instance from dependencies to ensure monkeypatching works
            _, auth, _, _, _ = get_dependencies()
            token = auth.login(username, password, client_id=_client_identifier(request))
            logger.info(f"Login successful for user: {username}")
            
            # Create response with redirect
            response = RedirectResponse(
                url="/app/upload",
                status_code=status.HTTP_303_SEE_OTHER
            )
            
            # Set cookie
            expires_delta = timedelta(minutes=auth.token_exp_minutes)
            expires_at = datetime.now(timezone.utc) + expires_delta
            
            response.set_cookie(
                key="access_token",
                value=token,
                httponly=True,
                samesite="lax",
                path="/",
                max_age=int(expires_delta.total_seconds()),
                expires=expires_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
            )
            
            logger.debug(f"Set cookie with token, expires in {auth.token_exp_minutes} minutes")
            return response

        except LoginRateLimitError:
            logger.warning(f"Login rate limited for user: {username}")
            response = templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Too many failed login attempts. Try again later.",
                    "is_authenticated": False
                },
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
            
        except AuthError:
            logger.warning(f"Login failed for user: {username}")
            response = templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Invalid username or password",
                    "is_authenticated": False
                }
            )
            # Prevent browser caching of error responses to ensure fresh error messages
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

    @app.post("/auth/login")
    async def auth_login_submit(request: Request):
        """Alternative login endpoint that forwards to the main login handler."""
        logger.info(f"/auth/login POST: forwarding to main login handler")
        return await login_post(request)

    @app.get("/logout")
    async def logout(request: Request):
        """Clears the authentication cookie and redirects to login."""
        response = RedirectResponse(
            url="/login", 
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
        response.delete_cookie("access_token")
        logger.info("User logged out, cookie cleared")
        return response

    @app.get("/dashboard")
    async def dashboard_page(request: Request):
        """Redirect the retired legacy dashboard to the reports workspace."""

        await get_current_active_user(request)
        return RedirectResponse(url="/app/reports", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @app.get("/upload")
    async def upload_page(request: Request):
        """Redirect the retired legacy upload page to the app upload workspace."""

        await get_current_active_user(request)
        return RedirectResponse(url="/app/upload", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @app.get("/app", response_class=HTMLResponse)
    async def app_root(request: Request):
        """Redirect authenticated app users to the upload workspace."""

        await get_current_active_user(request)
        return RedirectResponse(url="/app/upload", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @app.get("/app/upload", response_class=HTMLResponse)
    async def app_upload_page(request: Request):
        """Serve the prototype-modeled upload and process page."""

        config, _, _, _, _ = get_dependencies()
        return await render_app_page(
            request,
            "upload_process.html",
            page_title="Upload & Process",
            page_subtitle="Upload PDF files to split, extract data, and review results.",
            active_nav="upload",
            max_upload_mb=config.get("web.max_upload_mb", config.get("ui.max_upload_mb", 50)),
        )

    @app.get("/app/processing", response_class=HTMLResponse)
    async def app_processing_page(request: Request):
        """Serve the processing overview page."""

        return await render_app_page(
            request,
            "processing_overview.html",
            page_title="Processing Overview",
            page_subtitle="Track splitting, extraction, review, and completion state.",
            active_nav="upload",
        )

    @app.get("/app/batches/{batch_id}/split-results", response_class=HTMLResponse)
    async def app_split_results_page(request: Request, batch_id: str):
        """Serve split results for a batch."""

        return await render_app_page(
            request,
            "split_results.html",
            page_title="Split Results",
            page_subtitle="Inspect source PDFs and generated child documents.",
            active_nav="upload",
            batch_id=batch_id,
        )

    @app.get("/app/batches/{batch_id}", response_class=HTMLResponse)
    async def app_batch_processing_page(request: Request, batch_id: str):
        """Serve processing overview scoped to one batch."""

        return await render_app_page(
            request,
            "processing_overview.html",
            page_title="Processing Overview",
            page_subtitle="Track splitting, extraction, review, and completion state.",
            active_nav="upload",
            batch_id=batch_id,
        )

    @app.get("/app/documents/{document_id}/extraction", response_class=HTMLResponse)
    async def app_extraction_results_page(request: Request, document_id: str):
        """Serve persisted extraction results for one document."""

        return await render_app_page(
            request,
            "extraction_results.html",
            page_title="Extraction Results",
            page_subtitle="Inspect extracted fields and confidence values.",
            active_nav="upload",
            document_id=document_id,
        )

    @app.get("/app/review", response_class=HTMLResponse)
    async def app_review_queue_page(request: Request):
        """Serve the review queue page."""

        return await render_app_page(
            request,
            "review_queue.html",
            page_title="Review Queue",
            page_subtitle="Work documents that require human review.",
            active_nav="review",
        )

    @app.get("/app/review/{review_item_id}", response_class=HTMLResponse)
    async def app_human_review_page(request: Request, review_item_id: str):
        """Serve the human review workspace."""

        return await render_app_page(
            request,
            "human_review.html",
            page_title="Human Review",
            page_subtitle="Review source PDF content and corrected field values.",
            active_nav="review",
            review_item_id=review_item_id,
        )

    @app.get("/app/reports", response_class=HTMLResponse)
    async def app_reports_page(request: Request):
        """Serve the operator reports page."""

        return await render_app_page(
            request,
            "reports.html",
            page_title="Reports",
            page_subtitle="Review processing and review activity.",
            active_nav="reports",
        )

    @app.get("/app/settings/validation", response_class=HTMLResponse)
    async def app_config_validation_page(request: Request):
        """Serve the admin validation center page."""

        return await render_app_page(
            request,
            "config_validation.html",
            page_title="Validation Center",
            page_subtitle="Review configuration, schema, and pipeline findings.",
            active_nav="validation",
            admin_required=True,
        )

    @app.get("/app/settings", response_class=HTMLResponse)
    async def app_settings_page(request: Request):
        """Serve the operator settings page."""

        return await render_app_page(
            request,
            "settings.html",
            page_title="Settings",
            page_subtitle="View runtime settings for the current application.",
            active_nav="settings",
        )

    @app.get("/app/schemas", response_class=HTMLResponse)
    async def app_schema_editor_page(request: Request):
        """Serve the admin schema editor page."""

        return await render_app_page(
            request,
            "schema_editor.html",
            page_title="Schema Editor",
            page_subtitle="Manage schemas used by extraction review workflows.",
            active_nav="schemas",
            admin_required=True,
        )

    @app.get("/app/schemas/{schema_name}", response_class=HTMLResponse)
    async def app_named_schema_editor_page(request: Request, schema_name: str):
        """Serve the admin schema editor page for one schema."""

        return await render_app_page(
            request,
            "schema_editor.html",
            page_title="Schema Editor",
            page_subtitle="Manage schemas used by extraction review workflows.",
            active_nav="schemas",
            admin_required=True,
            schema_name=schema_name,
        )

    @app.get("/app/admin", response_class=HTMLResponse)
    async def app_admin_dashboard_page(request: Request):
        """Serve the admin dashboard."""

        return await render_app_page(
            request,
            "admin_dashboard.html",
            page_title="Admin",
            page_subtitle="Configuration health and governance overview.",
            active_nav="admin_home",
            admin_required=True,
        )

    @app.get("/app/admin/pipeline", response_class=HTMLResponse)
    async def app_pipeline_config_page(request: Request):
        """Serve the admin pipeline configuration page."""

        return await render_app_page(
            request,
            "pipeline_config.html",
            page_title="Pipeline",
            page_subtitle="Configure task order, enablement, and parameters.",
            active_nav="pipeline",
            admin_required=True,
        )

    @app.get("/app/admin/tasks", response_class=HTMLResponse)
    async def app_task_catalog_page(request: Request):
        """Serve the admin task catalog page."""

        return await render_app_page(
            request,
            "task_catalog.html",
            page_title="Task Catalog",
            page_subtitle="Inspect available workflow task classes.",
            active_nav="tasks",
            admin_required=True,
        )

    @app.get("/app/admin/review-gate", response_class=HTMLResponse)
    async def app_review_gate_rules_page(request: Request):
        """Serve the admin review gate rules page."""

        return await render_app_page(
            request,
            "review_gate_rules.html",
            page_title="Review Gate",
            page_subtitle="Configure review thresholds and review triggers.",
            active_nav="review_gate",
            admin_required=True,
        )

    @app.get("/app/admin/split", response_class=HTMLResponse)
    async def app_split_settings_page(request: Request):
        """Serve the admin split settings page."""

        return await render_app_page(
            request,
            "split_settings.html",
            page_title="Split Settings",
            page_subtitle="Configure split categories and adapter settings.",
            active_nav="split",
            admin_required=True,
        )

    @app.get("/app/admin/audit", response_class=HTMLResponse)
    async def app_admin_audit_page(request: Request):
        """Serve the admin audit history page."""

        return await render_app_page(
            request,
            "admin_audit.html",
            page_title="Admin Audit",
            page_subtitle="Inspect configuration and governance events.",
            active_nav="audit",
            admin_required=True,
        )

    @app.get("/app/admin/dry-run", response_class=HTMLResponse)
    async def app_pipeline_dry_run_page(request: Request):
        """Serve the admin review gate simulator page."""

        return await render_app_page(
            request,
            "pipeline_dry_run.html",
            page_title="Review Gate Simulator",
            page_subtitle="Run sample documents through draft pipeline decisions.",
            active_nav="dry_run",
            admin_required=True,
        )

    # Exception handler for authentication redirects
    from fastapi.responses import JSONResponse

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Custom handler to redirect to login on specific auth errors.

        For auth-related redirects we still return a redirect response and clear
        cookies where appropriate. For other HTTPExceptions (e.g. API errors)
        return a proper JSON response so API clients and tests receive a normal
        HTTP response instead of causing the exception to bubble up.

        HTTP Error Codes:
            - 307: Authentication required, redirects to login page
            - 400: Bad request (e.g., invalid input parameters)
            - 401: Authentication failed or token invalid
            - 404: Resource not found
            - 500: Internal server error
        """
        # Preserve the existing redirect handling for auth redirects
        if exc.status_code == status.HTTP_307_TEMPORARY_REDIRECT and exc.headers and exc.headers.get("Location") == "/login":
            response = RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
            # Clear cookie when redirecting due to token/credentials issues
            if isinstance(exc.detail, str) and ("token" in exc.detail.lower() or "credentials" in exc.detail.lower() or "authenticated" in exc.detail.lower()):
                response.delete_cookie("access_token")
            return response

        # For API usage and tests, return a JSON response with the same status and detail
        detail = exc.detail if exc.detail is not None else ""
        content = {"detail": detail}
        return JSONResponse(status_code=exc.status_code or 500, content=content)

    # API Router
    app.include_router(build_router())
    shutdown_manager = ShutdownManager()
    app.add_event_handler("shutdown", shutdown_manager.shutdown)

    return app


# Uvicorn entry helper for main.py / exposed ASGI application
app = create_app()
