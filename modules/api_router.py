"""API router setup for authentication, file upload, and status retrieval endpoints.

This module defines the FastAPI router and related dependencies for the web API.
It exposes the following endpoints:

- POST /login: Obtain an OAuth2 bearer token using username and password.
- POST /upload: Upload a PDF for processing; redirects to the dashboard page.
- GET /api/files: List files currently tracked in the processing directory with statuses.
- GET /api/status/{file_id}: Retrieve the processing status of a specific file.

Dependencies:
- ConfigManager: Loads and provides access to application configuration (e.g., folders, auth settings).
- AuthUtils: Handles authentication (login, token generation/validation).
- StatusManager: Accesses and aggregates file processing status metadata.
- WorkflowManager: Coordinates processing workflows used by file operations.
- FileProcessor: Handles web upload processing and integration with workflows.
- utils.retry_with_cleanup (optional): Retry wrapper used by FileProcessor if available.

All functions are documented using Google-style docstrings. No behavior is changed.

Architecture Reference:
    For detailed system architecture, API design patterns, and endpoint integration
    with the overall system, refer to docs/design_architecture.md.
"""

from typing import List, Dict, Any, Optional, Tuple
import os
import json
from pathlib import Path
import logging
import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from .auth_utils import AuthUtils, AuthError
from .config_manager import ConfigManager
from .status_manager import StatusManager
from .workflow_manager import WorkflowManager
from .file_processor import FileProcessor
from . import utils as utils_mod


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

    async def _parse_multipart_upload(request: Request) -> ParsedUpload:
        """Parse the multipart body and extract the uploaded file."""

        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported content type")

        body = await request.body()
        if not body:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload payload")

        header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode("latin-1", errors="ignore")
        message = BytesParser(policy=default).parsebytes(header_bytes + body)

        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            if part.get_param("name", header="content-disposition") != "file":
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
            return ParsedUpload(filename=filename, content_type=content, data=file_bytes)

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file field provided")

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

    @router.get("/api/files", response_model=List[FileStatus])
    def list_files(user: str = Depends(get_current_user)):
        """List current files and their statuses from the processing directory.

        Args:
            user: The authenticated user identifier, injected via dependency.

        Returns:
            List[FileStatus]: Collection of file status entries parsed from status files,
                              sorted by updated time (descending).

        Raises:
            HTTPException: 500 if the processing directory is misconfigured or inaccessible.

        HTTP Error Codes:
            - 200: Successful response with list of file statuses
            - 401: Authentication required or failed
            - 500: Processing directory misconfigured or inaccessible
        """
        
        config, _, _, _, _ = get_dependencies()
        processing_dir = config.get("watch_folder.processing_dir")
        if not processing_dir or not os.path.isdir(processing_dir):
            raise HTTPException(status_code=500, detail="Processing directory misconfigured")
        result: List[dict] = []
        # Enumerate *.txt status files
        for entry in os.listdir(processing_dir):
            if not entry.endswith(".txt"):
                continue
            file_id = entry[:-4]
            status_path = os.path.join(processing_dir, entry)
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Get original timestamps for sorting
                created_at_utc = (data.get("timestamps") or {}).get("created")
                updated_at_utc = (data.get("timestamps") or {}).get("pending")
                
                # Convert timestamps to Singapore time for display
                created_at_sg = convert_to_singapore_time(created_at_utc)
                updated_at_sg = convert_to_singapore_time(updated_at_utc)
                
                result.append({
                    "file_id": str(data.get("id") or file_id),
                    "original_name": data.get("original_filename"),
                    "status": data.get("status") or "Unknown",
                    "created_at": created_at_sg,
                    "updated_at": updated_at_sg,
                    "error": data.get("error"),
                    "created_at_utc": created_at_utc,  # Keep UTC for sorting
                    "updated_at_utc": updated_at_utc   # Keep UTC for sorting
                })
            except Exception:
                # Best-effort; skip corrupted files
                continue
        
        # Sort by updated_at_utc in descending order (latest first)
        # For files without updated_at_utc, use created_at_utc as fallback
        def get_sort_key(file_dict):
            # Use updated_at_utc if available, otherwise created_at_utc
            timestamp = file_dict.get("updated_at_utc") or file_dict.get("created_at_utc") or ""
            # Parse the timestamp for proper sorting
            if timestamp:
                try:
                    if timestamp.endswith('Z'):
                        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        return datetime.fromisoformat(timestamp)
                except Exception:
                    pass
            # Return epoch time for unparseable timestamps
            return datetime.min.replace(tzinfo=timezone.utc)
        
        result.sort(key=get_sort_key, reverse=True)
        
        # Convert back to FileStatus objects without the UTC fields
        file_status_result: List[FileStatus] = []
        for item in result:
            item.pop("created_at_utc", None)
            item.pop("updated_at_utc", None)
            file_status_result.append(FileStatus(**item))
        
        return file_status_result

    @router.get("/api/status/{file_id}")
    def get_status(file_id: str, user: str = Depends(get_current_user)):
        """Get the full processing status for a specific file including timestamps and details.

        Enhanced for modal dialog implementation: Returns complete status data instead of
        limited FileStatus model to provide rich information for the modal interface.
        Includes full timestamps, details object, and processing history for comprehensive
        status display in the UI.

        Args:
            file_id: The identifier of the file to query.
            user: The authenticated user identifier, injected via dependency.

        Returns:
            dict: The complete status information for the requested file including
                  timestamps, details, and all processing information. Structure:
                  {
                      "id": str,
                      "original_filename": str,
                      "status": str,
                      "timestamps": {"created": "...", "pending": "...", "created_sg": "..."},
                      "details": {...},
                      "error": str or null
                  }

        Raises:
            None: Graceful fallback implemented instead of exceptions.

        HTTP Error Codes:
            - 200: Successful response with full file status
            - 401: Authentication required or failed

        Note:
            - Returns placeholder status object if file exists but status not yet available
            - Converts all timestamps to Singapore time (GMT+8) for display
            - Thread-safe dictionary operations prevent iteration modification errors
        """
        _, _, status_mgr, _, _ = get_dependencies()
        r = status_mgr.get_status(file_id)

        if not r:
            raise HTTPException(status_code=404, detail="File not found")

        # Create a shallow copy to avoid mutating StatusManager state
        record = dict(r)

        # Extract and normalize timestamps with Singapore time conversion
        timestamps = dict(record.get("timestamps") or {})
        sg_timestamps: Dict[str, str] = {}
        for key, ts in timestamps.items():
            sg_timestamps[f"{key}_sg"] = convert_to_singapore_time(ts)
        if sg_timestamps:
            timestamps.update(sg_timestamps)  # Safe to update local copy

        return FileStatus(
            file_id=str(record.get("id") or file_id),
            original_name=record.get("original_filename"),
            status=record.get("status") or "Unknown",
            created_at=convert_to_singapore_time(timestamps.get("created")),
            updated_at=convert_to_singapore_time(timestamps.get("pending")),
            error=record.get("error"),
            timestamps=timestamps or None,
            details=record.get("details"),
        )

    return router
