# API endpoints
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlmodel import Session 
from app.services.media_service import MediaService
from app.models.media import Media 
from app.models.user import User # Import User model for dependency
from app.core.users import current_active_user # Import FastAPI-Users dependency
import logging 

# This will be properly set up in main.py by overriding this placeholder
# with the actual get_db_session from main.py's scope.
async def get_db_session() -> Session:
    pass 

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.post("/media/upload", response_model=Media)
async def upload_video(
    file: UploadFile = File(...),
    language: str = Form(...),
    # owner_id: int = Form(1), # Removed placeholder, will use authenticated user's ID
    db: Session = Depends(get_db_session),
    user: User = Depends(current_active_user) # FastAPI-Users dependency
):
    """
    Uploads a video file, saves it to S3, and creates a media record in the database.
    - **file**: The video file to upload.
    - **language**: The language of the video content (e.g., "en", "ja").
    Requires authentication. The media will be associated with the authenticated user.
    """
    if not db:
        logger.error(f"Database session not available for upload_video by user {user.id if user else 'unknown'}.")
        raise HTTPException(status_code=500, detail="Database not configured")

    media_service = MediaService(db_session=db)
    
    try:
        if not file.content_type.startswith("video/"):
            raise HTTPException(status_code=400, detail=f"Invalid file type: {file.content_type}. Please upload a video.")

        logger.info(f"User {user.id} uploading video. Language: {language}")
        created_media = await media_service.save_uploaded_video(
            file=file,
            owner_id=user.id, # Use authenticated user's ID
            language=language
        )
        
        try:
            from workers.tasks import extract_audio_task
            extract_audio_task.delay(created_media.id)
            logger.info(f"Successfully queued audio extraction for media_id: {created_media.id} (user: {user.id})")
        except Exception as e_celery:
            logger.error(f"Failed to queue audio extraction for media_id {created_media.id} (user: {user.id}): {str(e_celery)}")

        return created_media
    except HTTPException as e:
        logger.error(f"HTTPException during file upload for user {user.id}: {e.detail}")
        raise e 
    except Exception as e:
        logger.error(f"Unexpected error during file upload for user {user.id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/media/{media_id}", response_model=Media)
async def get_media_status(
    media_id: int, 
    db: Session = Depends(get_db_session),
    user: User = Depends(current_active_user) # FastAPI-Users dependency
):
    """
    Retrieves a media record by its ID to check its processing status.
    Only the owner of the media can access this endpoint.
    """
    logger.info(f"User {user.id} attempting to retrieve media with id: {media_id}")
    
    if not db:
        logger.error(f"Database session not available for get_media_status (media_id: {media_id}, user: {user.id}).")
        raise HTTPException(status_code=500, detail="Database not configured")

    media_record = db.get(Media, media_id)
    
    if not media_record:
        logger.warning(f"Media record with id: {media_id} not found (requested by user: {user.id}).")
        raise HTTPException(status_code=404, detail=f"Media with id {media_id} not found")
    
    # Ownership check
    if media_record.owner_id != user.id:
        # Optional: Admins could bypass this check if is_superuser is implemented and checked.
        # if not user.is_superuser: 
        logger.warning(f"User {user.id} attempted to access media {media_id} owned by {media_record.owner_id}. Access denied.")
        raise HTTPException(status_code=403, detail="Not authorized to access this media")
    
    logger.info(f"User {user.id} successfully retrieved media record with id: {media_id}, title: {media_record.title}")
    return media_record


# --- Endpoints for Pre-signed URLs ---
from app.schemas.media_schemas import MediaURLResponse # Response model for URLs
from app.core.s3_client import generate_presigned_url, get_s3_client # S3 utilities
from app.core.config import settings # For S3_BUCKET_NAME

@router.get("/media/{media_id}/video-url", response_model=MediaURLResponse)
async def get_media_video_url(
    media_id: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(current_active_user),
    s3_client = Depends(get_s3_client) # Inject S3 client
):
    """
    Generates a pre-signed URL to access the original video file for a media item.
    Requires ownership.
    """
    logger.info(f"User {user.id} requesting video URL for media_id: {media_id}")
    if not db:
        logger.error(f"DB session not available for video-url (media_id: {media_id}, user: {user.id}).")
        raise HTTPException(status_code=500, detail="Database not configured")
    if not s3_client:
        logger.error(f"S3 client not available for video-url (media_id: {media_id}, user: {user.id}).")
        raise HTTPException(status_code=500, detail="S3 service not available")

    media_record = db.get(Media, media_id)
    if not media_record:
        logger.warning(f"Video-URL: Media {media_id} not found (user: {user.id}).")
        raise HTTPException(status_code=404, detail=f"Media with id {media_id} not found")

    if media_record.owner_id != user.id:
        logger.warning(f"Video-URL: User {user.id} attempt to access media {media_id} owned by {media_record.owner_id}. Denied.")
        raise HTTPException(status_code=403, detail="Not authorized to access this media resource")

    if not media_record.source_path:
        logger.warning(f"Video-URL: Media {media_id} has no source_path (video S3 key) (user: {user.id}).")
        raise HTTPException(status_code=404, detail="Video file not available for this media")

    presigned_url = generate_presigned_url(
        bucket_name=settings.S3_BUCKET_NAME,
        object_name=media_record.source_path,
        expiration=600, # 10 minutes
        s3_client=s3_client
    )

    if not presigned_url:
        logger.error(f"Video-URL: Failed to generate presigned URL for media {media_id}, S3 key {media_record.source_path} (user: {user.id}).")
        raise HTTPException(status_code=500, detail="Could not generate video URL")
    
    logger.info(f"Video-URL: Successfully generated for media {media_id} (user: {user.id}).")
    return MediaURLResponse(url=presigned_url)


@router.get("/media/{media_id}/webvtt-url", response_model=MediaURLResponse)
async def get_media_webvtt_url(
    media_id: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(current_active_user),
    s3_client = Depends(get_s3_client) # Inject S3 client
):
    """
    Generates a pre-signed URL to access the WebVTT file for a media item.
    Requires ownership.
    """
    logger.info(f"User {user.id} requesting WebVTT URL for media_id: {media_id}")
    if not db:
        logger.error(f"DB session not available for webvtt-url (media_id: {media_id}, user: {user.id}).")
        raise HTTPException(status_code=500, detail="Database not configured")
    if not s3_client:
        logger.error(f"S3 client not available for webvtt-url (media_id: {media_id}, user: {user.id}).")
        raise HTTPException(status_code=500, detail="S3 service not available")

    media_record = db.get(Media, media_id)
    if not media_record:
        logger.warning(f"WebVTT-URL: Media {media_id} not found (user: {user.id}).")
        raise HTTPException(status_code=404, detail=f"Media with id {media_id} not found")

    if media_record.owner_id != user.id:
        logger.warning(f"WebVTT-URL: User {user.id} attempt to access media {media_id} owned by {media_record.owner_id}. Denied.")
        raise HTTPException(status_code=403, detail="Not authorized to access this media resource")

    if not media_record.webvtt_path:
        logger.warning(f"WebVTT-URL: Media {media_id} has no webvtt_path (WebVTT S3 key) (user: {user.id}).")
        raise HTTPException(status_code=404, detail="WebVTT file not available for this media")

    presigned_url = generate_presigned_url(
        bucket_name=settings.S3_BUCKET_NAME,
        object_name=media_record.webvtt_path,
        expiration=600, # 10 minutes
        s3_client=s3_client
    )

    if not presigned_url:
        logger.error(f"WebVTT-URL: Failed to generate presigned URL for media {media_id}, S3 key {media_record.webvtt_path} (user: {user.id}).")
        raise HTTPException(status_code=500, detail="Could not generate WebVTT URL")
        
    logger.info(f"WebVTT-URL: Successfully generated for media {media_id} (user: {user.id}).")
    return MediaURLResponse(url=presigned_url)
