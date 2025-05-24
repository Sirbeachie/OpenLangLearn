# API endpoints
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlmodel import Session # Will be used for dependency injection
from app.services.media_service import MediaService
from app.models.media import Media # For response model
import logging # For logging

# Placeholder for database session dependency - this will be properly set up in main.py
# For now, this allows type hinting and endpoint definition.
async def get_db_session() -> Session:
    # This is a placeholder. In a real app, this would yield a database session.
    # For example, using a context manager with SQLAlchemy/SQLModel.
    # from app.main import create_db_and_tables # Assuming this function exists
    # with Session(engine) as session: # engine needs to be defined
    #     yield session
    # For now, we'll raise an error if it's actually called without proper setup
    # raise NotImplementedError("get_db_session not implemented yet in endpoints.py, will be in main.py")
    # For the purpose of this step, we will assume a session is passed.
    # This will be connected in main.py
    pass 

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    return {"status": "ok"}

# Define a response model for the upload endpoint if needed, or directly return the Media object
# For now, we'll return a dictionary for simplicity, but Pydantic models are better.

@router.post("/media/upload", response_model=Media) # Using Media as response model
async def upload_video(
    file: UploadFile = File(...),
    language: str = Form(...),
    owner_id: int = Form(1), # Defaulting owner_id to 1 as a placeholder
    db: Session = Depends(get_db_session) # Placeholder for DB session
):
    """
    Uploads a video file, saves it, and creates a media record in the database.
    - **file**: The video file to upload.
    - **language**: The language of the video content (e.g., "en", "ja").
    - **owner_id**: The ID of the user uploading the file (placeholder).
    """
    if not db:
        # This check is for the interim period before main.py fully sets up DB injection
        logger.error("Database session not available for upload_video.")
        raise HTTPException(status_code=500, detail="Database not configured")

    media_service = MediaService(db_session=db)
    
    try:
        # Basic validation for file type, can be expanded
        if not file.content_type.startswith("video/"):
            raise HTTPException(status_code=400, detail=f"Invalid file type: {file.content_type}. Please upload a video.")

        created_media = await media_service.save_uploaded_video(
            file=file,
            owner_id=owner_id,
            language=language
        )
        # Return the full Media object, FastAPI will serialize it based on response_model
        
        # Trigger Celery task for audio extraction
        try:
            from workers.tasks import extract_audio_task
            extract_audio_task.delay(created_media.id)
            logger.info(f"Successfully queued audio extraction task for media_id: {created_media.id}")
        except Exception as e_celery:
            # Log the error but don't fail the upload request itself
            # The main operation (upload) was successful.
            # Background task queuing failure should be handled separately (e.g., monitoring, retries)
            logger.error(f"Failed to queue audio extraction task for media_id {created_media.id}: {str(e_celery)}")

        return created_media
    except HTTPException as e:
        logger.error(f"HTTPException during file upload: {e.detail}")
        raise e # Re-raise HTTPException
    except Exception as e:
        logger.error(f"An unexpected error occurred during file upload: {str(e)}")
        # It's good practice to log the stack trace for unexpected errors
        # import traceback
        # logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/media/{media_id}", response_model=Media)
async def get_media_status(media_id: int, db: Session = Depends(get_db_session)):
    """
    Retrieves a media record by its ID to check its processing status.
    The presence of `audio_path`, `transcription_path`, and `webvtt_path`
    indicates the completion of different processing stages.
    """
    logger.info(f"Attempting to retrieve media with id: {media_id}")
    
    if not db:
        # This check is for the interim period before main.py fully sets up DB injection
        # (Though by this point, it should be fully set up)
        logger.error(f"Database session not available for get_media_status (media_id: {media_id}).")
        raise HTTPException(status_code=500, detail="Database not configured")

    media_record = db.get(Media, media_id)
    
    if not media_record:
        logger.warning(f"Media record with id: {media_id} not found.")
        raise HTTPException(status_code=404, detail=f"Media with id {media_id} not found")
    
    logger.info(f"Successfully retrieved media record with id: {media_id}, title: {media_record.title}")
    return media_record
