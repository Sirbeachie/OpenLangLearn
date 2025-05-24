# app/api/files_api.py
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.core.config import Settings, settings as global_settings # Import global settings for conditional registration too
from app.core.users import current_active_user
from app.models.user import User
from app.models.media import Media
# Assuming get_db_session will be overridden in main.py
from app.api.endpoints import get_db_session # Or from wherever it's defined

logger = logging.getLogger(__name__)
router = APIRouter()

# Dependency to get current settings (useful if settings could change per request, though unlikely here)
# For simplicity, we can also import global_settings directly if preferred for module-level constants.
def get_settings_dependency() -> Settings:
    return global_settings

@router.get("/static-files/{file_path:path}", response_class=FileResponse)
async def serve_local_static_file(
    file_path: str, # FastAPI captures the full path here
    current_user: User = Depends(current_active_user),
    db: Session = Depends(get_db_session),
    app_settings: Settings = Depends(get_settings_dependency) # Inject settings
):
    """
    Serves a static file from local storage if STORAGE_TYPE is 'local'.
    This endpoint is only active and functional when local storage is configured.
    It performs an ownership check to ensure the requesting user has a media record
    that references the requested file path.
    """
    if app_settings.STORAGE_TYPE != "local":
        logger.warning(f"Attempt to access local file serving endpoint when STORAGE_TYPE is '{app_settings.STORAGE_TYPE}'. Denying request for path: {file_path}")
        raise HTTPException(status_code=404, detail="Local file serving not active.")

    # Validate that the user owns a media item that references this file_path
    # The file_path from the URL is the relative path stored in one of Media's path fields.
    
    # Using .as_posix() to ensure consistent path separator for DB query,
    # assuming paths are stored with forward slashes (as per LocalStorageService.save_file).
    normalized_file_path = Path(file_path).as_posix()

    query = select(Media).where(
        Media.owner_id == current_user.id,
        (Media.source_path == normalized_file_path) |
        (Media.audio_path == normalized_file_path) |
        (Media.webvtt_path == normalized_file_path) |
        (Media.transcription_path == normalized_file_path)
    )
    media_record_referencing_file = db.exec(query).first()

    if not media_record_referencing_file:
        logger.warning(f"User {current_user.id} tried to access file '{normalized_file_path}' but no owned media record references it or file does not exist.")
        raise HTTPException(status_code=404, detail="File not found or access denied.")

    # Construct the full, absolute path to the file on the server
    # LOCAL_STORAGE_PATH is already resolved in settings
    full_local_path = app_settings.LOCAL_STORAGE_PATH / normalized_file_path
    
    # Security Check: Ensure the resolved path is still within the intended base directory
    # and that it's an actual file.
    try:
        resolved_full_local_path = full_local_path.resolve(strict=True) # strict=True ensures it exists
        base_path_resolved = app_settings.LOCAL_STORAGE_PATH.resolve()

        # Check if the resolved path is truly within the base storage path
        # For Python 3.9+ Path.is_relative_to() is preferred.
        # For older versions, a string check on resolved paths is a common method.
        if not str(resolved_full_local_path).startswith(str(base_path_resolved)):
             logger.error(f"Directory traversal attempt detected for path '{normalized_file_path}' by user {current_user.id}. Resolved: {resolved_full_local_path}, Base: {base_path_resolved}")
             raise HTTPException(status_code=404, detail="File not found (invalid path).")

        if not resolved_full_local_path.is_file():
            logger.warning(f"Requested path '{normalized_file_path}' is not a file for user {current_user.id}. Resolved: {resolved_full_local_path}")
            raise HTTPException(status_code=404, detail="File not found (not a file).")
            
    except FileNotFoundError: # From resolve(strict=True)
        logger.warning(f"File not found at resolved path for '{normalized_file_path}' (user {current_user.id}). Path: {full_local_path}")
        raise HTTPException(status_code=404, detail="File not found.")
    except Exception as e: # Catch other potential errors during path resolution
        logger.error(f"Error resolving path for '{normalized_file_path}' (user {current_user.id}): {e}")
        raise HTTPException(status_code=500, detail="Internal server error processing file path.")

    logger.info(f"Serving file '{resolved_full_local_path}' to user {current_user.id}")
    return FileResponse(resolved_full_local_path)
