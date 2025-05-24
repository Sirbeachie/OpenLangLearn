# Subtitle and Word models
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from app.models.media import Media # Added to ensure Relationship can use Media
from sqlalchemy import UniqueConstraint # Import UniqueConstraint

class Word(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lemma", "language", name="uq_word_lemma_language"),)
    
    id: int = Field(default=None, primary_key=True)
    lemma: str = Field(index=True) # The dictionary form of the word
    language: str = Field(index=True) # Language of the lemma, e.g., 'en', 'ja'
    # Add other fields like part_of_speech if needed globally for words,
    # or keep token-specific details in the language plugin's output / subtitle cue.

class SubtitleCue(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    media_id: int = Field(foreign_key="media.id", index=True)
    start_ms: int # Start time of the cue in milliseconds
    end_ms: int   # End time of the cue in milliseconds
    text_markdown: str # The cue text, with tokens wrapped in spans for interactivity

    # Define relationship to Media if needed, though not explicitly requested for this model
    # media: Optional[Media] = Relationship(back_populates="subtitle_cues") # Requires "subtitle_cues" in Media model

    # If you want to link words directly to cues (many-to-many), you'd need a link table.
    # For now, word information is embedded in text_markdown via IDs.
