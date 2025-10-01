"""FastAPI application entry module.

Responsibilities:
- Provide an app factory to construct the FastAPI application.
- Configure and mount static and template directories (Jinja2).
- Set up permissive CORS for local development.
- Define simple HTML routes: login, dashboard, and upload.
- Include API routes assembled via modules.api_router.build_router().
- Register graceful shutdown hook via ShutdownManager.
"""

from pathlib import Path
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from modules.api_router import build_router, get_dependencies
from modules.shutdown_manager import ShutdownManager
from modules.config_manager import ConfigManager
from modules.auth_utils import AuthUtils, AuthError


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
        - CORS is permissive (allow all origins, methods, and headers) to
          simplify local development.
        - API routes are composed via modules.api_router.build_router().
        - ShutdownManager is registered to handle application shutdown events.
    """
    app = FastAPI(title="PDF Processing Web Interface", version="1.0.0")

    # Static and Templates
    static_dir = Path("web/static")
    templates_dir = Path("web/templates")
    static_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))

    # CORS (allow localhost by default)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    logger = logging.getLogger("web.server")

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

    # --- Routes ---

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Redirects to dashboard if logged in, otherwise to login page."""
        username = await get_current_user(request)
        if username:
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        else:
            return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        """Serves the login page."""
        username = await get_current_user(request)
        if username:
            logger.info(f"/login GET: user already authenticated -> {username}, redirecting to /dashboard")
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        
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

    @app.post("/login")
    async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
        """Handles login form submission, verifies credentials, sets cookie, redirects.
        
        On successful authentication: sets HttpOnly cookie and redirects to dashboard.
        On authentication failure: returns login page with error message and cache-control headers
        to prevent browser caching of error responses.
        """
        logger.info(f"Login attempt for username: {username}")
        
        try:
            # Get auth instance from dependencies to ensure monkeypatching works
            _, auth, _, _, _ = get_dependencies()
            token = auth.login(username, password)
            logger.info(f"Login successful for user: {username}")
            
            # Create response with redirect
            response = RedirectResponse(
                url="/dashboard",
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
    async def auth_login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
        """Alternative login endpoint that forwards to the main login handler."""
        logger.info(f"/auth/login POST: forwarding to main login handler")
        return await login_post(request, username, password)

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

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        """Serves the dashboard page, requires authentication."""
        try:
            username = await get_current_active_user(request)
            logger.info(f"/dashboard GET: authenticated user={username}")
            return templates.TemplateResponse(
                "dashboard.html", 
                {"request": request, "is_authenticated": True, "username": username}
            )
        except HTTPException as e:
            if e.status_code == status.HTTP_307_TEMPORARY_REDIRECT:
                return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
            raise

    @app.get("/upload", response_class=HTMLResponse)
    async def upload_page(request: Request):
        """Serves the upload page, requires authentication."""
        try:
            username = await get_current_active_user(request)
            logger.info(f"/upload GET: authenticated user={username}")
            return templates.TemplateResponse(
                "upload.html", 
                {"request": request, "is_authenticated": True, "username": username}
            )
        except HTTPException as e:
            if e.status_code == status.HTTP_307_TEMPORARY_REDIRECT:
                return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
            raise

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