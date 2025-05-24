# Media service
import os
import shutil
from fastapi import UploadFile
from sqlmodel import Session
from app.models.media import Media
from datetime import datetime

UPLOAD_DIRECTORY = "media_uploads"

class MediaService:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    async def save_uploaded_video(self, file: UploadFile, owner_id: int, language: str) -> Media:
        os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)
        
        file_path = os.path.join(UPLOAD_DIRECTORY, file.filename)
        
        # Save the uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        media_entry = Media(
            owner_id=owner_id,
            title=file.filename, # Using filename as title for now
            language=language,
            kind="video", # Explicitly setting kind to 'video'
            source_path=file_path,
            # transcription_path will be updated later
            created_at=datetime.utcnow() # Ensure created_at is set
        )
        
        self.db_session.add(media_entry)
        self.db_session.commit()
        self.db_session.refresh(media_entry)
        
        return media_entry

    # Placeholder for create_media, can be removed or refactored if save_uploaded_video covers its intent
    # async def create_media(self, filename: str, file_path: str, user_id: int):
    #     # Logic to create and store media record
    #     pass

    async def get_media_by_id(self, media_id: int) -> Media | None:
        # Logic to retrieve media by ID
        return self.db_session.get(Media, media_id)
