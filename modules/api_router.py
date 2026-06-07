"""API router setup for authentication, file upload, and status retrieval endpoints.

This module defines the FastAPI router and related dependencies for the web API.
It exposes the following endpoints:

- POST /login: Obtain an OAuth2 bearer token using username and password.
- POST /upload: Upload a PDF for processing; redirects to the dashboard page.
- GET /api/files: Legacy compatibility list backed by SQLite documents.
- GET /api/status/{file_id}: Legacy compatibility status backed by SQLite documents.

Dependencies:
- ConfigManager: Loads and provides access to application configuration (e.g., folders, auth settings).
- AuthUtils: Handles authentication (login, token generation/validation).
- StatusManager: Legacy compatibility dependency retained for older callers.
- WorkflowManager: Coordinates processing workflows used by file operations.
- FileProcessor: Handles web upload processing and integration with workflows.
- utils.retry_with_cleanup (optional): Retry wrapper used by FileProcessor if available.

All functions are documented using Google-style docstrings.

Architecture Reference:
    For detailed system architecture, API design patterns, and endpoint integration
    with the overall system, refer to docs/design_architecture.md.
"""

from typing import List, Dict, Any, Optional, Tuple, cast
import os
import json
from pathlib import Path
import logging
import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from .auth_utils import AuthUtils, AuthError
from .config_manager import ConfigManager
from .status_manager import StatusManager
from .workflow_manager import WorkflowManager
from .file_processor import FileProcessor
from . import utils as utils_mod
from .db.connection import connect
from .db.connection import json_loads
from .db.repositories import DocumentRepository, ExtractionRepository, ReviewRepository, TaskRunRepository
from .db.migrations import initialize_database
from .services.admin_settings_service import (
    AdminAuditService,
    AdminSettingsError,
    AdminSettingsService,
    AdminSummaryService,
    PipelineDryRunService,
)
from .services.audit_service import AuditService
from .services.batch_service import BatchService
from .services.config_validation_service import ConfigValidationService
from .services.pipeline_config_service import PipelineConfigError, PipelineConfigService
from .services.processing_state_service import ProcessingStateService, build_pipeline_snapshot
from .services.reports_service import ReportsService
from .services.review_service import ReviewService, ReviewServiceError
from .services.runtime_settings_service import RuntimeSettingsService
from .services.schema_service import SchemaService
from .services.task_catalog_service import TaskCatalogService
from .resume_manager import ResumeManager


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

# Custom dependency to get token from either header or cookie
class CookieOrHeaderTokenBearer:
    """Custom token bearer that extracts token from Authorization header or cookie."""
    
    async def __call__(self, request: Request) -> Optional[str]:
        """Extract token from Authorization header or access_token cookie.
        
        Args:
            request: The FastAPI request object
            
        Returns:
            The token string if found, None otherwise
        """
        # First try to get token from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "")
        
        # If not in header, try to get from cookie
        token = request.cookies.get("access_token")
        if token:
            return token
        
        # No token found
        return None

# Create an instance of our custom token bearer
cookie_or_header_token = CookieOrHeaderTokenBearer()


class TokenResponse(BaseModel):
    """OAuth2 access token response.

    Attributes:
        access_token: The JWT or opaque token issued upon successful authentication.
        token_type: The type of token; always "bearer" for OAuth2 flows here.
        expires_in: Token expiration time in seconds.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UploadResponse(BaseModel):
    """Response for successful file upload.

    Attributes:
        file_id: Unique identifier assigned to the uploaded file.
        status: Initial status after upload; typically "Pending".
    """

    file_id: str
    status: str = "Pending"


class FileStatus(BaseModel):
    """Represents the processing status of a file.

    Attributes:
        file_id: Unique identifier of the file being tracked.
        original_name: Original filename provided at upload time, if available.
        status: Current processing status (e.g., Pending, Processing, Completed, Failed).
        created_at: ISO8601 timestamp for when the file was first registered.
        updated_at: ISO8601 timestamp for last known status update.
        error: Error message if processing failed or encountered issues.
        timestamps: Dictionary of timestamp information including created, pending, and SG time conversions.
        details: Dictionary containing additional processing details and metadata.
    """

    file_id: str
    original_name: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error: Optional[str] = None
    timestamps: Optional[Dict[str, Any]] = None
    details: Optional[Dict[str, Any]] = None

def convert_to_singapore_time(utc_time_str: Optional[str]) -> str:
    """Convert UTC time string to Singapore time format (dd-mm-yyyy hh:mm:ss GMT+8).

    Accepts None and returns an empty string in that case.
    """
    if not utc_time_str:
        return ""
    try:
        # Parse the UTC time string
        if utc_time_str.endswith('Z'):
            utc_time = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
        else:
            utc_time = datetime.fromisoformat(utc_time_str)
        
        # Convert to Singapore time (UTC+8)
        singapore_time = utc_time.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
        
        # Format as dd-mm-yyyy hh:mm:ss GMT+8
        return singapore_time.strftime("%d-%m-%Y %H:%M:%S GMT+8")
    except Exception:
        # Return original string if parsing fails
        return utc_time_str

def get_dependencies() -> tuple:
    """Construct and return core application dependencies.

    This centralizes dependency creation to support test injection/mocking and
    keeps route handlers concise.

    Returns:
        Tuple[ConfigManager, AuthUtils, StatusManager, WorkflowManager, FileProcessor]:
        A tuple containing initialized instances for configuration, authentication,
        status access, workflow coordination, and file processing.

    Raises:
        None
    """
    cfg_env = os.getenv("CONFIG_PATH")
    cfg_path = Path(cfg_env) if cfg_env else Path("config.yaml")
    config = ConfigManager(config_path=cfg_path.resolve())
    if bool(config.get("database.run_migrations_on_startup", True)):
        initialize_database(config)
    auth = AuthUtils(config)
    status_mgr = StatusManager(config)
    # WorkflowManager signature expects config_manager
    workflow_mgr = WorkflowManager(config_manager=config)
    # Provide a basic retry function from utils if available, else a no-op passthrough
    retry_func = getattr(utils_mod, "retry_with_cleanup", None)
    if retry_func is None:
        retry_func = lambda func, *a, **kw: func(*a, **kw)
    file_processor = FileProcessor(config_manager=config, retry_operation_func=retry_func, workflow_manager=workflow_mgr)
    return config, auth, status_mgr, workflow_mgr, file_processor


def get_current_user(token: Optional[str] = Depends(cookie_or_header_token), auth: AuthUtils = Depends(lambda: get_dependencies()[1])) -> str:
    """Resolve the current user from a bearer token or cookie.

    Args:
        token: Bearer token extracted from Authorization header or access_token cookie.
        auth: Authentication utility used to validate and parse the token.

    Returns:
        The authenticated username or user identifier as a string.

    Raises:
        HTTPException: If the token is invalid, missing, or expired (401 Unauthorized).
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Not authenticated"
        )
    
    try:
        return auth.get_current_user(token)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def _as_string_list(value: Any) -> list[str]:
    """Normalize config role values into strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return []


def is_admin_user(username: str, config: Any) -> bool:
    """Return whether a user can access admin APIs."""
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


def require_admin_user(user: str, config: Any) -> None:
    """Raise a 403 when the current user lacks admin access."""
    if not is_admin_user(user, config):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


def _file_status_from_document(document: dict[str, Any], *, details: dict[str, Any] | None = None) -> FileStatus:
    """Convert a SQLite document row into the legacy FileStatus response shape."""
    timestamps = {
        "created": document.get("created_at"),
        "updated": document.get("updated_at"),
        "created_sg": convert_to_singapore_time(document.get("created_at")),
        "updated_sg": convert_to_singapore_time(document.get("updated_at")),
    }
    return FileStatus(
        file_id=str(document["id"]),
        original_name=document.get("original_filename") or Path(str(document.get("file_path") or "")).name,
        status=str(document.get("status") or "unknown"),
        created_at=convert_to_singapore_time(document.get("created_at")),
        updated_at=convert_to_singapore_time(document.get("updated_at")),
        error=details.get("error") if details else None,
        timestamps=timestamps,
        details=details,
    )


def _confidence_band(confidence: Any) -> str:
    """Map numeric confidence to UI badge bands."""
    if confidence is None:
        return "missing"
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return "missing"
    if value >= 0.90:
        return "high"
    if value >= 0.70:
        return "medium"
    return "low"


def _parsed_field_payload(field: dict[str, Any]) -> dict[str, Any]:
    """Return a UI-ready extracted field payload."""
    confidence = field.get("confidence")
    return {
        "id": field.get("id"),
        "field_key": field.get("field_key"),
        "field_alias": field.get("field_alias"),
        "extracted_value": json_loads(field.get("extracted_value_json")),
        "corrected_value": json_loads(field.get("corrected_value_json")),
        "final_value": json_loads(field.get("final_value_json")),
        "confidence": confidence,
        "confidence_label": field.get("confidence_label"),
        "confidence_band": _confidence_band(confidence),
        "requires_review": bool(field.get("requires_review")),
        "review_status": field.get("review_status"),
        "source": json_loads(field.get("source_json"), {}),
        "created_at": field.get("created_at"),
        "updated_at": field.get("updated_at"),
    }


def _parsed_file_payload(file_record: dict[str, Any]) -> dict[str, Any]:
    """Return a UI-ready document file payload."""
    return {
        "id": file_record.get("id"),
        "file_type": file_record.get("file_type"),
        "file_path": file_record.get("file_path"),
        "filename": Path(str(file_record.get("file_path") or "")).name,
        "created_at": file_record.get("created_at"),
        "metadata": json_loads(file_record.get("metadata_json"), {}),
    }


# Background task function to process the uploaded file
def process_file_in_background(file_processor: FileProcessor, temp_path: str, file_id: str, original_filename: Optional[str]) -> None:
    """Process the uploaded file in the background.
    
    Args:
        file_processor: The FileProcessor instance
        temp_path: Path to the temporarily saved file
        file_id: The file ID to use for processing
        original_filename: The original filename of the uploaded file
    """
    logger = logging.getLogger("api_router")
    try:
        logger.info(f"Processing file {file_id} in the background")
        
        # Get the processing directory from config
        config, _, _, _, _ = get_dependencies()
        processing_dir = str(config.get('watch_folder.processing_dir'))
        if not processing_dir:
            raise ValueError("watch_folder.processing_dir is not configured")
        
        # Generate the final filename
        final_name = f"{file_id}.pdf"
        final_processing_path = os.path.join(processing_dir, final_name)
        
        # Move the file from temp location to processing directory
        os.replace(temp_path, final_processing_path)
        
        # Process the file (create status and trigger workflow)
        file_processor.process_file(
            filepath=final_processing_path,
            unique_id=file_id,
            source="web",
            original_filename=original_filename
        )
        
        logger.info(f"File {file_id} processed successfully in the background")
    except Exception as e:
        logger.error(f"Error processing file {file_id} in the background: {e}")
        # Clean up the temp file if it still exists
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def build_router() -> APIRouter:
    """Build and return the FastAPI router with all API endpoints.

    Returns:
        APIRouter: Configured router including login, upload, list files, and status endpoints.

    Raises:
        None

    Architecture Reference:
        For detailed system architecture, API design patterns, and endpoint integration
        with the overall system, refer to docs/design_architecture.md.
    """
    router = APIRouter()
    logger = logging.getLogger("api_router")

    async def _extract_login_credentials(request: Request) -> Tuple[str, str]:
        """Extract username and password from supported payload formats."""

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

    @dataclass
    class ParsedUpload:
        """Simple data container for a parsed upload payload."""

        filename: str
        content_type: str
        data: bytes

    async def _parse_multipart_uploads(
        request: Request,
        *,
        field_names: set[str] | None = None,
    ) -> list[ParsedUpload]:
        """Parse the multipart body and extract one or more uploaded files."""

        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported content type")

        body = await request.body()
        if not body:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload payload")

        header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode("latin-1", errors="ignore")
        message = cast(EmailMessage, BytesParser(policy=cast(Any, default)).parsebytes(header_bytes + body))
        accepted_names = field_names or {"file"}
        uploads: list[ParsedUpload] = []

        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            if part.get_param("name", header="content-disposition") not in accepted_names:
                continue
            filename = part.get_filename() or "uploaded_file"
            # get_payload(decode=True) may return bytes or (rarely) str/other types depending on part.
            # Normalize to bytes to satisfy type expectations and avoid Pylance type errors.
            raw_payload = part.get_payload(decode=True)
            if isinstance(raw_payload, (bytes, bytearray)):
                file_bytes = bytes(raw_payload)
            elif raw_payload is None:
                file_bytes = b""
            else:
                # Fallback: convert to str then encode.
                try:
                    file_bytes = str(raw_payload).encode("utf-8", errors="ignore")
                except Exception:
                    file_bytes = b""
            content = part.get_content_type() or "application/octet-stream"
            uploads.append(ParsedUpload(filename=filename, content_type=content, data=file_bytes))

        if not uploads:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file field provided")
        return uploads

    async def _parse_multipart_upload(request: Request) -> ParsedUpload:
        """Parse the multipart body and extract the uploaded file."""

        return (await _parse_multipart_uploads(request, field_names={"file"}))[0]

    async def _json_body(request: Request) -> dict[str, Any]:
        """Parse an optional JSON request body."""
        body = await request.body()
        if not body:
            return {}
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON payload must be an object")
        return payload

    def _schema_active_review_warning(schema_name: str, config: ConfigManager) -> dict[str, Any] | None:
        """Return a warning when open review items reference a schema."""
        with connect(config) as conn:
            reviews = ReviewRepository(conn).list_queue()
        open_items = []
        for item in reviews:
            if item.get("status") not in {"pending", "in_review"}:
                continue
            metadata = json_loads(item.get("metadata_json"), {})
            if metadata.get("schema_file") == schema_name:
                open_items.append(item["id"])
        if not open_items:
            return None
        return {
            "message": "Schema changes may affect active review items.",
            "active_review_count": len(open_items),
            "review_item_ids": open_items,
        }

    def _schema_audit_payload(schema_name: str, service: SchemaService) -> dict[str, Any]:
        """Return compact schema metadata for admin audit events."""
        normalized = service.normalize_schema(schema_name)
        return {
            "schema_name": schema_name,
            "title": normalized.get("title") if normalized else None,
            "hash": service.schema_hash(schema_name),
            "field_count": len(normalized.get("fields", [])) if normalized else 0,
        }

    def _append_admin_audit(
        config: ConfigManager,
        *,
        event_type: str,
        user: str | None,
        before: Any = None,
        after: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append an admin audit event without changing endpoint response shape."""
        initialize_database(config)
        with connect(config) as conn:
            AuditService(conn).append_event(
                event_type=event_type,
                user=user,
                before=before,
                after=after,
                metadata=metadata,
            )

    def _schema_payload(payload: dict[str, Any]) -> dict[str, Any]:
        schema = payload.get("schema")
        if schema is None:
            schema = {key: value for key, value in payload.items() if key not in {"name", "new_name"}}
        if not isinstance(schema, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Schema payload must be an object")
        schema.setdefault("fields", {})
        return schema

    def _validation_summary(findings: list[dict[str, Any]]) -> dict[str, int]:
        """Return error/warning/info counts for normalized findings."""
        return {
            "errors": sum(1 for finding in findings if finding.get("severity", finding.get("level")) == "error"),
            "warnings": sum(1 for finding in findings if finding.get("severity", finding.get("level")) == "warning"),
            "info": sum(1 for finding in findings if finding.get("severity", finding.get("level")) == "info"),
        }

    @router.post("/api/login", response_model=TokenResponse)
    async def login(request: Request):
        """Authenticate a user and return an access token.

        Args:
            request: The FastAPI request object containing login credentials.

        Returns:
            TokenResponse: Contains the bearer access token, token type, and expiration.

        Raises:
            HTTPException: 401 if credentials are invalid.

        HTTP Error Codes:
            - 200: Successful authentication, returns access token
            - 401: Invalid credentials provided
        """
        username, password = await _extract_login_credentials(request)
        if not username or not password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credentials")

        _, auth, _, _, _ = get_dependencies()
        try:
            token = auth.login(username, password)
            exp_minutes = auth.token_exp_minutes
            return TokenResponse(access_token=token, expires_in=exp_minutes * 60)
        except AuthError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    @router.post("/upload")
    async def upload_pdf(
        request: Request,
        background_tasks: BackgroundTasks,
        user: str = Depends(get_current_user),
    ):
        """Upload a PDF file for processing.

        Args:
            background_tasks: FastAPI BackgroundTasks for processing the file asynchronously.
            file: The uploaded PDF file.
            user: The authenticated user identifier, injected via dependency.

        Returns:
            RedirectResponse: Redirects to the dashboard page immediately after file upload.

        Raises:
            HTTPException: 400 if the upload or processing fails.

        HTTP Error Codes:
            - 303: Successful upload, redirects to dashboard
            - 400: Invalid PDF file or upload/processing failure
            - 401: Authentication required or failed
        """
        config, _, _, _, file_processor = get_dependencies()
        try:
            upload = await _parse_multipart_upload(request)
            # Generate a UUID for the file
            file_id = str(uuid.uuid4())
            
            # Get the upload directory from config
            upload_dir = str(config.get('web.upload_dir'))
            if not upload_dir:
                raise ValueError("web.upload_dir is not configured")
            
            # Create a temporary path for the uploaded file
            temp_filename = f"{file_id}_temp.pdf"
            temp_path = os.path.join(upload_dir, temp_filename)
            
            # Save the uploaded file immediately to the temporary location
            with open(temp_path, "wb") as out_f:
                out_f.write(upload.data)
            
            # Validate PDF header before scheduling background processing.
            # Use 5 bytes ('%PDF-'), 3 attempts and 0.2s delay to match watch-folder behavior.
            try:
                if not utils_mod.is_pdf_header(temp_path, read_size=5, attempts=3, delay=0.2):
                    # remove temp file and return a 400 to the client
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                    raise HTTPException(status_code=400, detail="Invalid PDF header")
            except HTTPException:
                # re-raise known HTTP errors
                raise
            except Exception as e:
                # Any unexpected validation error -> cleanup and respond 400
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass
                logger.error(f"PDF header validation error: {e}")
                raise HTTPException(status_code=400, detail="Invalid PDF header")
            # Reset file pointer to beginning for any future reads
            # Log the successful immediate save
            logger.info(f"File saved immediately with ID: {file_id}")

            # Add the processing task to background tasks
            background_tasks.add_task(process_file_in_background, file_processor, temp_path, file_id, upload.filename)
            
            # Redirect to dashboard page immediately after upload
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @router.post("/api/batches/upload")
    async def upload_pdf_batch(
        request: Request,
        background_tasks: BackgroundTasks,
        user: str = Depends(get_current_user),
    ):
        """Upload one or more PDFs as a single SQLite-backed processing batch."""
        config, _, _, _, file_processor = get_dependencies()
        uploads = await _parse_multipart_uploads(request, field_names={"files", "file"})
        processing_dir = str(config.get("watch_folder.processing_dir") or "")
        if not processing_dir:
            raise HTTPException(status_code=500, detail="Processing directory misconfigured")
        Path(processing_dir).mkdir(parents=True, exist_ok=True)

        file_descriptors: list[dict[str, Any]] = []
        saved_paths: list[str] = []
        try:
            for index, upload in enumerate(uploads):
                original_filename = os.path.basename(upload.filename or f"uploaded_{index + 1}.pdf")
                if not original_filename.lower().endswith(".pdf"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{original_filename} is not a PDF file",
                    )
                if not upload.data.startswith(b"%PDF-"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{original_filename} has an invalid PDF header",
                    )

                document_id = str(uuid.uuid4())
                final_path = str(Path(processing_dir, f"{document_id}.pdf").resolve())
                with open(final_path, "wb") as out_file:
                    out_file.write(upload.data)
                saved_paths.append(final_path)
                file_descriptors.append(
                    {
                        "document_id": document_id,
                        "file_path": final_path,
                        "original_filename": original_filename,
                        "status": "queued",
                        "metadata": {
                            "legacy_id": document_id,
                            "ingestion_source": "web",
                            "uploaded_by": user,
                            "content_type": upload.content_type,
                            "size_bytes": len(upload.data),
                        },
                    }
                )

            with connect(config) as conn:
                created = BatchService(conn).create_ingestion_batch_with_documents(
                    source="web",
                    files=file_descriptors,
                    metadata={
                        "uploaded_by": user,
                        "file_count": len(file_descriptors),
                        "pipeline_snapshot": build_pipeline_snapshot(config),
                    },
                    status="queued",
                )

            batch = created["batch"]
            documents = created["documents"]
            for descriptor, document in zip(file_descriptors, documents):
                background_tasks.add_task(
                    file_processor.process_file,
                    filepath=descriptor["file_path"],
                    unique_id=document["id"],
                    source="web",
                    original_filename=descriptor["original_filename"],
                    batch_id=batch["id"],
                    document_id=document["id"],
                    create_sqlite_state=False,
                )

            return {
                "batch_id": batch["id"],
                "document_ids": [document["id"] for document in documents],
                "status": "queued",
            }
        except HTTPException:
            for path in saved_paths:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    logger.warning("Failed to remove rejected upload file: %s", path)
            raise
        except Exception as exc:
            for path in saved_paths:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    logger.warning("Failed to remove upload file after error: %s", path)
            logger.error("Batch upload failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.get("/api/files", response_model=List[FileStatus])
    def list_files(user: str = Depends(get_current_user)):
        """List current documents through the legacy file-status shape.

        Args:
            user: The authenticated user identifier, injected via dependency.

        Returns:
            List[FileStatus]: Collection of SQLite-backed document status
            entries sorted by update time descending.
        """
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            documents = DocumentRepository(conn).list_all(limit=500)
        return [_file_status_from_document(document) for document in documents]

    @router.get("/api/config/validation")
    def validate_active_config(user: str = Depends(get_current_user)):
        """Validate the active configuration file for admin/UI diagnostics."""
        config, _, _, _, _ = get_dependencies()
        return ConfigValidationService(config).validate_active_config()

    @router.post("/api/config/validation")
    async def validate_config_payload(request: Request, user: str = Depends(get_current_user)):
        """Validate a submitted config payload or YAML document."""
        config, _, _, _, _ = get_dependencies()
        payload = await _json_body(request)
        try:
            return ConfigValidationService(config).validate_payload(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.post("/api/pipeline/validate")
    async def validate_pipeline_payload(request: Request, user: str = Depends(get_current_user)):
        """Validate pipeline-specific rules for a submitted config payload."""
        config, _, _, _, _ = get_dependencies()
        payload = await _json_body(request)
        try:
            return ConfigValidationService(config).validate_pipeline(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.get("/api/reports/summary")
    def get_reports_summary(user: str = Depends(get_current_user)):
        """Return SQLite-backed processing report summary metrics."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            return ReportsService(conn).summary()

    @router.get("/api/settings")
    def get_runtime_settings(user: str = Depends(get_current_user)):
        """Return read-only non-secret runtime settings."""
        config, _, _, _, _ = get_dependencies()
        return RuntimeSettingsService(config).settings()

    @router.get("/api/admin/task-catalog")
    def get_admin_task_catalog(user: str = Depends(get_current_user)):
        """Return available workflow task classes for admin pipeline editing."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        return TaskCatalogService(config).catalog()

    @router.get("/api/admin/summary")
    def get_admin_summary(user: str = Depends(get_current_user)):
        """Return admin dashboard summary data."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        with connect(config) as conn:
            return AdminSummaryService(config, conn).summary()

    @router.get("/api/admin/settings")
    def get_admin_settings(user: str = Depends(get_current_user)):
        """Return editable non-secret admin settings."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        with connect(config) as conn:
            return AdminSettingsService(config, conn).get_admin_settings()

    @router.put("/api/admin/settings")
    async def update_admin_settings(request: Request, user: str = Depends(get_current_user)):
        """Update editable non-secret admin settings."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        try:
            with connect(config) as conn:
                return AdminSettingsService(config, conn).update_admin_settings(payload, user=user)
        except AdminSettingsError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.get("/api/admin/audit")
    def get_admin_audit(
        event_type: str | None = None,
        audit_user: str | None = Query(default=None, alias="user"),
        created_from: str | None = None,
        created_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
        user: str = Depends(get_current_user),
    ):
        """Return filtered admin audit events."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        with connect(config) as conn:
            return AdminAuditService(conn).list_events(
                event_type=event_type,
                user=audit_user,
                created_from=created_from,
                created_to=created_to,
                limit=limit,
                offset=offset,
            )

    @router.post("/api/admin/dry-run")
    async def run_admin_pipeline_dry_run(request: Request, user: str = Depends(get_current_user)):
        """Run a non-mutating draft pipeline dry run."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        try:
            with connect(config) as conn:
                return PipelineDryRunService(config, conn).run(payload, user=user)
        except PipelineConfigError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": str(exc), "findings": exc.findings},
            )

    def _pipeline_model_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
        """Return an optional pipeline model from API payload shapes."""
        if not payload:
            return None
        model = payload.get("model", payload)
        if not isinstance(model, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pipeline model must be an object")
        return model

    @router.get("/api/admin/pipeline")
    def get_admin_pipeline(user: str = Depends(get_current_user)):
        """Return active and draft pipeline configuration for admin editing."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        with connect(config) as conn:
            service = PipelineConfigService(config, conn)
            payload = service.get_pipeline()
        payload["catalog"] = TaskCatalogService(config).catalog()
        return payload

    @router.put("/api/admin/pipeline/draft")
    async def save_admin_pipeline_draft(request: Request, user: str = Depends(get_current_user)):
        """Create or update a pipeline draft."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        model = _pipeline_model_payload(payload)
        try:
            with connect(config) as conn:
                service = PipelineConfigService(config, conn)
                draft = service.create_draft(user=user) if model is None else service.save_draft(model, user=user)
                return {"draft": draft}
        except PipelineConfigError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.post("/api/admin/pipeline/diff")
    async def diff_admin_pipeline(request: Request, user: str = Depends(get_current_user)):
        """Return active-vs-draft pipeline diff."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        model = _pipeline_model_payload(payload)
        try:
            with connect(config) as conn:
                return PipelineConfigService(config, conn).diff(model)
        except PipelineConfigError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.post("/api/admin/pipeline/validate")
    async def validate_admin_pipeline(request: Request, user: str = Depends(get_current_user)):
        """Validate a pipeline draft."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        model = _pipeline_model_payload(payload)
        try:
            with connect(config) as conn:
                return PipelineConfigService(config, conn).validate_draft(model, user=user, audit=True)
        except PipelineConfigError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.post("/api/admin/pipeline/publish")
    async def publish_admin_pipeline(request: Request, user: str = Depends(get_current_user)):
        """Publish a validated pipeline draft."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        model = _pipeline_model_payload(payload)
        try:
            with connect(config) as conn:
                return PipelineConfigService(config, conn).publish(model, user=user)
        except PipelineConfigError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": str(exc), "findings": exc.findings},
            )

    @router.get("/api/admin/review-gate-rules")
    def get_admin_review_gate_rules(user: str = Depends(get_current_user)):
        """Return admin-editable review gate rules."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        with connect(config) as conn:
            return AdminSettingsService(config, conn).get_review_gate_rules()

    @router.put("/api/admin/review-gate-rules")
    async def update_admin_review_gate_rules(request: Request, user: str = Depends(get_current_user)):
        """Update admin-editable review gate rules."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        try:
            with connect(config) as conn:
                return AdminSettingsService(config, conn).update_review_gate_rules(payload, user=user)
        except AdminSettingsError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.get("/api/admin/split-settings")
    def get_admin_split_settings(user: str = Depends(get_current_user)):
        """Return admin-editable non-secret LlamaCloud Split settings."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        with connect(config) as conn:
            return AdminSettingsService(config, conn).get_split_settings()

    @router.put("/api/admin/split-settings")
    async def update_admin_split_settings(request: Request, user: str = Depends(get_current_user)):
        """Update admin-editable non-secret LlamaCloud Split settings."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        try:
            with connect(config) as conn:
                return AdminSettingsService(config, conn).update_split_settings(payload, user=user)
        except AdminSettingsError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.post("/api/admin/split-settings/test-connection")
    async def test_admin_split_connection(request: Request, user: str = Depends(get_current_user)):
        """Run a non-invasive Split adapter readiness check."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        await _json_body(request)
        with connect(config) as conn:
            return AdminSettingsService(config, conn).test_split_connection(user=user)

    @router.get("/api/admin/schemas/validation")
    def get_admin_schema_validation(user: str = Depends(get_current_user)):
        """Validate all configured review schemas for the admin validation center."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        result = ConfigValidationService(config).validate_all_schemas()
        findings = cast(list[dict[str, Any]], result.get("findings", []))
        return {
            "source": "schemas",
            "valid": bool(result.get("valid", False)),
            "summary": _validation_summary(findings),
            "findings": findings,
            "schemas": SchemaService(config).list_schemas(),
        }

    @router.post("/api/admin/schemas/validate-all")
    async def validate_all_admin_schemas(request: Request, user: str = Depends(get_current_user)):
        """Run all-schema validation from the admin validation center."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        await _json_body(request)
        result = ConfigValidationService(config).validate_all_schemas()
        findings = cast(list[dict[str, Any]], result.get("findings", []))
        response = {
            "source": "schemas",
            "valid": bool(result.get("valid", False)),
            "summary": _validation_summary(findings),
            "findings": findings,
            "schemas": SchemaService(config).list_schemas(),
        }
        _append_admin_audit(
            config,
            event_type="admin_schemas_validated",
            user=user,
            after={"valid": response["valid"], "summary": response["summary"]},
            metadata={"schema_count": len(response["schemas"])},
        )
        return response

    @router.get("/api/schemas")
    def list_schemas(user: str = Depends(get_current_user)):
        """List configured review schemas."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        return {"schemas": SchemaService(config).list_schemas()}

    @router.post("/api/schemas")
    async def create_schema(request: Request, user: str = Depends(get_current_user)):
        """Create a new review schema file."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        schema_name = str(payload.get("name") or "").strip()
        if not schema_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Schema name is required")
        service = SchemaService(config)
        try:
            schema = service.save_schema(schema_name, _schema_payload(payload), overwrite=False)
        except FileExistsError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        _append_admin_audit(
            config,
            event_type="admin_schema_created",
            user=user,
            after=_schema_audit_payload(schema_name, service),
        )
        return {"schema": schema, "content": service.schema_content(schema_name)}

    @router.post("/api/schemas/{schema_name}/validate")
    async def validate_schema_payload(schema_name: str, request: Request, user: str = Depends(get_current_user)):
        """Validate a schema draft without saving it."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        schema = _schema_payload(payload)
        service = SchemaService(config)
        findings = service.validate_schema(schema)
        response = {
            "valid": not findings,
            "findings": findings,
            "active_review_warning": _schema_active_review_warning(schema_name, config),
        }
        _append_admin_audit(
            config,
            event_type="admin_schema_validated",
            user=user,
            after={"schema_name": schema_name, "valid": response["valid"], "summary": _validation_summary(findings)},
            metadata={"finding_paths": [finding.get("path") for finding in findings]},
        )
        return response

    @router.post("/api/schemas/{schema_name}/duplicate")
    async def duplicate_schema(schema_name: str, request: Request, user: str = Depends(get_current_user)):
        """Duplicate an existing review schema."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        payload = await _json_body(request)
        new_name = str(payload.get("new_name") or payload.get("name") or "").strip()
        if not new_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New schema name is required")
        service = SchemaService(config)
        before = _schema_audit_payload(schema_name, service)
        try:
            schema = service.duplicate_schema(schema_name, new_name)
        except FileExistsError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        _append_admin_audit(
            config,
            event_type="admin_schema_duplicated",
            user=user,
            before=before,
            after=_schema_audit_payload(new_name, service),
            metadata={"source_schema_name": schema_name},
        )
        return {"schema": schema, "content": service.schema_content(new_name)}

    @router.get("/api/schemas/{schema_name}")
    def get_schema(schema_name: str, user: str = Depends(get_current_user)):
        """Return one normalized review schema and raw content."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        service = SchemaService(config)
        schema = service.normalize_schema(schema_name)
        if schema is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schema not found")
        return {
            "schema": schema,
            "raw_schema": service.load_schema(schema_name),
            "content": service.schema_content(schema_name),
            "active_review_warning": _schema_active_review_warning(schema_name, config),
        }

    @router.put("/api/schemas/{schema_name}")
    async def update_schema(schema_name: str, request: Request, user: str = Depends(get_current_user)):
        """Update an existing review schema file."""
        config, _, _, _, _ = get_dependencies()
        require_admin_user(user, config)
        service = SchemaService(config)
        if service.load_schema(schema_name) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schema not found")
        before = _schema_audit_payload(schema_name, service)
        payload = await _json_body(request)
        try:
            schema = service.save_schema(schema_name, _schema_payload(payload), overwrite=True)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        after = _schema_audit_payload(schema_name, service)
        _append_admin_audit(
            config,
            event_type="admin_schema_updated",
            user=user,
            before=before,
            after=after,
            metadata={"active_review_warning": _schema_active_review_warning(schema_name, config)},
        )
        return {
            "schema": schema,
            "content": service.schema_content(schema_name),
            "active_review_warning": _schema_active_review_warning(schema_name, config),
        }

    @router.get("/api/status/{file_id}")
    def get_status(file_id: str, user: str = Depends(get_current_user)):
        """Get SQLite-backed document status through the legacy status shape.

        Args:
            file_id: The identifier of the file to query.
            user: The authenticated user identifier, injected via dependency.

        Returns:
            FileStatus: Legacy-compatible response whose ``details`` field
            includes document metadata, task runs, and registered artifacts.
        """
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            documents = DocumentRepository(conn)
            task_runs = TaskRunRepository(conn)
            document = documents.get(file_id)
            if document is None:
                document = documents.get(str(file_id))
            if document is None:
                raise HTTPException(status_code=404, detail="File not found")
            runs = task_runs.list_by_document(str(document["id"]))
            files = [_parsed_file_payload(file_record) for file_record in documents.list_files(str(document["id"]))]

        failed_runs = [run for run in runs if run.get("status") == "failed"]
        latest_error = failed_runs[-1].get("error") if failed_runs else None
        details = {
            "legacy_endpoint": True,
            "state_source": "sqlite",
            "document": document,
            "task_runs": runs,
            "files": files,
            "error": latest_error,
        }
        return _file_status_from_document(document, details=details)

    @router.get("/api/batches")
    def list_batches(user: str = Depends(get_current_user)):
        """List SQLite-backed ingestion batches."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            return BatchService(conn).list_batches()

    @router.get("/api/batches/{batch_id}")
    def get_batch(batch_id: str, user: str = Depends(get_current_user)):
        """Return one SQLite-backed ingestion batch."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            batch = BatchService(conn).get_batch(batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="Batch not found")
        return batch

    @router.get("/api/batches/{batch_id}/documents")
    def list_batch_documents(batch_id: str, user: str = Depends(get_current_user)):
        """List documents belonging to a SQLite-backed ingestion batch."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            service = BatchService(conn)
            if service.get_batch(batch_id) is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            return service.list_documents(batch_id)

    @router.get("/api/processing-state")
    def list_processing_state(
        limit: int = Query(default=10, ge=1, le=50),
        user: str = Depends(get_current_user),
    ):
        """Return recent batch processing state for the dynamic pipeline UI."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            return ProcessingStateService(config, conn).list_active_state(limit=limit)

    @router.get("/api/batches/{batch_id}/processing-state")
    def get_batch_processing_state(batch_id: str, user: str = Depends(get_current_user)):
        """Return dynamic pipeline processing state for one batch."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            payload = ProcessingStateService(config, conn).get_batch_state(batch_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="Batch not found")
        return payload

    @router.get("/api/batches/{batch_id}/split-results")
    def get_split_results(batch_id: str, user: str = Depends(get_current_user)):
        """Return split parent/child results for one batch."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            batch_service = BatchService(conn)
            batch = batch_service.get_batch(batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            documents = DocumentRepository(conn)
            batch_documents = documents.list_by_batch(batch_id)

        roots = [doc for doc in batch_documents if not doc.get("parent_document_id")]
        children_by_parent: Dict[str, list[dict[str, Any]]] = {}
        for document in batch_documents:
            parent_id = document.get("parent_document_id")
            if parent_id:
                children_by_parent.setdefault(str(parent_id), []).append(document)

        sources = []
        total_children = 0
        failed_children = 0
        for root in roots:
            children = children_by_parent.get(str(root["id"]), [])
            child_payloads = []
            for child in children:
                total_children += 1
                if child.get("status") == "failed":
                    failed_children += 1
                child_metadata = json_loads(child.get("metadata_json"), {})
                child_payloads.append(
                    {
                        "document_id": child["id"],
                        "filename": child.get("original_filename"),
                        "file_path": child.get("file_path"),
                        "category": child.get("split_category"),
                        "page_start": child.get("page_start"),
                        "page_end": child.get("page_end"),
                        "pages": child_metadata.get("split_pages") or [],
                        "split_confidence": child.get("split_confidence"),
                        "status": child.get("status"),
                        "parent_document_id": child.get("parent_document_id"),
                    }
                )
            source_status = "success" if root.get("status") == "split_completed" else root.get("status")
            sources.append(
                {
                    "document_id": root["id"],
                    "source_file": root.get("original_filename"),
                    "file_path": root.get("file_path"),
                    "documents_created": len(children),
                    "status": source_status,
                    "children": child_payloads,
                }
            )

        return {
            "summary": {
                "total_files": len(roots),
                "documents_created": total_children,
                "successful": total_children - failed_children,
                "failed": failed_children,
            },
            "sources": sources,
        }

    @router.get("/api/documents/{document_id}/task-runs")
    def list_document_task_runs(document_id: str, user: str = Depends(get_current_user)):
        """List task runs for one document."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            return TaskRunRepository(conn).list_by_document(document_id)

    @router.get("/api/documents/{document_id}/extraction")
    def get_document_extraction(document_id: str, user: str = Depends(get_current_user)):
        """Return persisted extraction details for one document."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            documents = DocumentRepository(conn)
            extractions = ExtractionRepository(conn)
            reviews = ReviewRepository(conn)
            document = documents.get(document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found")

            latest_result = extractions.get_latest_result(document_id)
            fields = [_parsed_field_payload(field) for field in extractions.get_fields(document_id)]
            files = [_parsed_file_payload(file_record) for file_record in documents.list_files(document_id)]
            open_review = reviews.find_open_for_document(document_id)
            siblings = [
                {
                    "id": sibling["id"],
                    "label": sibling.get("original_filename") or Path(str(sibling.get("file_path") or "")).name or sibling["id"],
                    "status": sibling.get("status"),
                }
                for sibling in documents.list_by_batch(str(document["batch_id"]))
            ]

        filename = document.get("original_filename") or Path(str(document.get("file_path") or "")).name
        return {
            "document": {
                "id": document["id"],
                "batch_id": document.get("batch_id"),
                "parent_document_id": document.get("parent_document_id"),
                "filename": filename,
                "document_type": document.get("document_type"),
                "status": document.get("status"),
                "file_path": document.get("file_path"),
                "page_start": document.get("page_start"),
                "page_end": document.get("page_end"),
                "split_category": document.get("split_category"),
                "split_confidence": document.get("split_confidence"),
                "preview_url": f"/api/documents/{document_id}/file/pdf",
                "metadata": json_loads(document.get("metadata_json"), {}),
            },
            "files": files,
            "siblings": siblings,
            "latest_extraction": {
                "id": latest_result.get("id"),
                "provider": latest_result.get("provider"),
                "provider_job_id": latest_result.get("provider_job_id"),
                "task_run_id": latest_result.get("task_run_id"),
                "data": json_loads(latest_result.get("data_json"), {}),
                "metadata": json_loads(latest_result.get("metadata_json"), {}),
                "created_at": latest_result.get("created_at"),
            }
            if latest_result
            else None,
            "fields": fields,
            "review_item_id": open_review.get("id") if open_review else None,
        }

    @router.get("/api/documents/{document_id}/file/pdf")
    def get_document_pdf_file(document_id: str, user: str = Depends(get_current_user)):
        """Serve the current document PDF for preview from registered SQLite state."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            documents = DocumentRepository(conn)
            document = documents.get(document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found")
            files = documents.list_files(document_id)

        candidate_paths = [
            file_record.get("file_path")
            for file_record in files
            if file_record.get("file_type") in {"split_pdf", "source_original", "original_pdf"}
        ]
        candidate_paths.append(document.get("file_path"))
        for raw_path in candidate_paths:
            if not raw_path:
                continue
            path = Path(str(raw_path))
            if path.exists() and path.is_file():
                return FileResponse(str(path), media_type="application/pdf", filename=path.name)
        raise HTTPException(status_code=404, detail="PDF file not found")

    @router.get("/api/documents/{document_id}/fields")
    def list_document_fields(document_id: str, user: str = Depends(get_current_user)):
        """List persisted extracted fields for one document."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            fields = ExtractionRepository(conn).get_fields(document_id)
        for field in fields:
            for key in ("extracted_value_json", "corrected_value_json", "final_value_json", "source_json"):
                field[key.replace("_json", "")] = json_loads(field.get(key))
        return fields

    @router.post("/api/documents/{document_id}/resume")
    def resume_document(document_id: str, user: str = Depends(get_current_user)):
        """Resume a reviewed document from the next configured pipeline task."""
        config, _, _, _, _ = get_dependencies()
        return {"resumed": ResumeManager(config).resume_document(document_id, user=user)}

    @router.get("/api/review/items")
    def list_review_items(
        status: str | None = None,
        queue_name: str | None = None,
        user: str = Depends(get_current_user),
    ):
        """List review items with optional status and queue filters."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            return ReviewService(conn, config).list_items(status=status, queue_name=queue_name)

    @router.get("/api/review/items/{review_item_id}")
    def get_review_item(review_item_id: str, user: str = Depends(get_current_user)):
        """Return review item detail."""
        config, _, _, _, _ = get_dependencies()
        with connect(config) as conn:
            detail = ReviewService(conn, config).get_detail(review_item_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Review item not found")
        return detail

    @router.post("/api/review/items/{review_item_id}/claim")
    async def claim_review_item(review_item_id: str, request: Request, user: str = Depends(get_current_user)):
        """Claim a review item for the current user."""
        config, _, _, _, _ = get_dependencies()
        payload = await _json_body(request)
        operator = str(payload.get("user") or user)
        try:
            with connect(config) as conn:
                return ReviewService(conn, config).claim(review_item_id, operator)
        except ReviewServiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @router.post("/api/review/items/{review_item_id}/release")
    async def release_review_item(review_item_id: str, request: Request, user: str = Depends(get_current_user)):
        """Release a review item lock."""
        config, _, _, _, _ = get_dependencies()
        payload = await _json_body(request)
        operator = str(payload.get("user") or user)
        try:
            with connect(config) as conn:
                ReviewService(conn, config).release(review_item_id, operator)
        except ReviewServiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"released": True}

    @router.post("/api/review/items/{review_item_id}/draft")
    async def save_review_draft(review_item_id: str, request: Request, user: str = Depends(get_current_user)):
        """Save review draft corrections without resuming."""
        config, _, _, _, _ = get_dependencies()
        payload = await _json_body(request)
        operator = str(payload.get("user") or user)
        corrections = cast(dict[str, Any], payload.get("corrections") or {})
        try:
            with connect(config) as conn:
                return ReviewService(conn, config).save_draft(review_item_id, operator, corrections)
        except ReviewServiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @router.post("/api/review/items/{review_item_id}/diff")
    async def preview_review_diff(review_item_id: str, request: Request, user: str = Depends(get_current_user)):
        """Preview review correction differences."""
        config, _, _, _, _ = get_dependencies()
        payload = await _json_body(request)
        corrections = cast(dict[str, Any], payload.get("corrections") or {})
        with connect(config) as conn:
            return ReviewService(conn, config).diff_preview(review_item_id, corrections)

    @router.post("/api/review/items/{review_item_id}/complete")
    async def complete_review_item(review_item_id: str, request: Request, user: str = Depends(get_current_user)):
        """Complete review, persist corrections, and trigger resume."""
        config, _, _, _, _ = get_dependencies()
        payload = await _json_body(request)
        operator = str(payload.get("user") or user)
        corrections = cast(dict[str, Any], payload.get("corrections") or {})
        try:
            with connect(config) as conn:
                return ReviewService(conn, config).complete(review_item_id, operator, corrections)
        except ReviewServiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    return router
