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
from app.core.storage_service import StorageInterface # Import StorageInterface

class MediaService:
    def __init__(self, db_session: Session, storage_service: StorageInterface):
        self.db_session = db_session
        # self.s3_client = get_s3_client() # REMOVED: S3 client is now part of StorageService
        self.storage_service = storage_service

    async def save_uploaded_video(self, file: UploadFile, owner_id: int, language: str) -> Media:
        # if not self.s3_client: # Replaced with storage_service check if needed, but factory should handle it
        #     logger.error("MediaService: S3 client not available. Cannot upload video.")
        #     raise HTTPException(status_code=500, detail="S3 storage service not configured.")

        safe_filename = os.path.basename(file.filename) if file.filename else "untitled_video"
        
        # Define destination path (S3 key or local relative path)
        # This path structure is consistent for both S3 and local storage.
        destination_path = f"uploads/user_{owner_id}/{safe_filename}"
        
        try:
            # Use the storage service to save the file
            # file.file is a SpooledTemporaryFile, which is file-like and works with upload_fileobj
            stored_path = await self.storage_service.save_file(
                file_obj=file.file, 
                destination_path=destination_path
            )
        except (ConnectionError, IOError) as e: # Catch errors from storage service
            logger.error(f"Failed to save video '{safe_filename}' via storage service for owner {owner_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save video: {e}")
            
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
