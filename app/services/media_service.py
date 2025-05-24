# Media service
import os
# import shutil # No longer needed for local file copy
from fastapi import UploadFile, HTTPException
from sqlmodel import Session
from app.models.media import Media
from datetime import datetime
from app.core.config import settings
from app.core.s3_client import upload_file_to_s3, get_s3_client # Import S3 utility
import logging

logger = logging.getLogger(__name__)

# UPLOAD_DIRECTORY = "media_uploads" # No longer saving locally first for uploads

class MediaService:
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.s3_client = get_s3_client() # Initialize S3 client once per service instance

    async def save_uploaded_video(self, file: UploadFile, owner_id: int, language: str) -> Media:
        if not self.s3_client:
            logger.error("MediaService: S3 client not available. Cannot upload video.")
            raise HTTPException(status_code=500, detail="S3 storage service not configured.")

        # Sanitize filename slightly, though S3 handles most characters.
        # Consider more robust slugification if needed.
        safe_filename = os.path.basename(file.filename) if file.filename else "untitled_video"
        
        # Define S3 object key
        s3_object_key = f"uploads/user_{owner_id}/{safe_filename}"
        
        # Upload the file stream directly to S3
        # file.file is a SpooledTemporaryFile, which is file-like
        success = upload_file_to_s3(
            file_path_or_obj=file.file, 
            bucket_name=settings.S3_BUCKET_NAME, 
            object_name=s3_object_key,
            s3_client=self.s3_client
        )
        
        if not success:
            logger.error(f"Failed to upload video '{safe_filename}' to S3 for owner {owner_id}.")
            raise HTTPException(status_code=500, detail="Failed to upload video to S3.")
            
        media_entry = Media(
            owner_id=owner_id,
            title=safe_filename, 
            language=language,
            kind="video", 
            source_path=s3_object_key, # Store S3 object key as source_path
            created_at=datetime.utcnow()
        )
        
        self.db_session.add(media_entry)
        self.db_session.commit()
        self.db_session.refresh(media_entry)
        
        logger.info(f"Video '{safe_filename}' (owner: {owner_id}) uploaded to S3 ({s3_object_key}) and DB record created (id: {media_entry.id}).")
        return media_entry

    async def get_media_by_id(self, media_id: int) -> Media | None:
        return self.db_session.get(Media, media_id)
