# Media model
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Media(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id") # Placeholder for user relationship
    title: str # Original filename or user-provided title
    language: str # Language of the media content (e.g., 'en', 'ja')
    kind: str # Type of media (e.g., 'video', 'audio', 'youtube_url')
    source_path: str # Path to the original media file on the server
    transcription_path: Optional[str] = None # Path to the generated transcription file
    audio_path: Optional[str] = None # Path to the extracted audio file
    webvtt_path: Optional[str] = None # Path to the generated WebVTT file
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
