# app/models/familiarity.py
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.subtitle import Word # Assuming Word model is in subtitle.py

class Familiarity(SQLModel, table=True):
    user_id: int = Field(default=None, primary_key=True, foreign_key="user.id")
    word_id: int = Field(default=None, primary_key=True, foreign_key="word.id")
    
    # Score from 1 (least familiar) to 5 (most familiar/mastered)
    score: int = Field(gt=0, le=5) 
    
    # Timestamp for when the record was last updated
    # default_factory is used for initial creation.
    # For updates, this needs to be handled manually in the service layer.
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})

    # Define relationships if needed for ORM features, though not strictly required for this task
    # user: Optional["User"] = Relationship(back_populates="familiarities") # Requires "familiarities" in User model
    # word: Optional["Word"] = Relationship(back_populates="familiarities") # Requires "familiarities" in Word model

    class Config:
        # For Pydantic V1, use orm_mode = True
        # For Pydantic V2, use from_attributes = True
        orm_mode = True
        # If using Pydantic V2, you would use:
        # model_config = {"from_attributes": True}
