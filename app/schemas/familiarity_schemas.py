# app/schemas/familiarity_schemas.py
from pydantic import BaseModel, Field as PydanticField # Rename to avoid clash with SQLModel Field
from sqlmodel import SQLModel, Field as SQLModelField # SQLModel's Field
from datetime import datetime

class FamiliarityBase(SQLModel):
    score: int = SQLModelField(gt=0, le=5, description="Familiarity score from 1 (least) to 5 (most).")

class FamiliarityRead(FamiliarityBase):
    user_id: int
    word_id: int
    updated_at: datetime

    class Config:
        orm_mode = True # For Pydantic V1
        # For Pydantic V2, use: model_config = {"from_attributes": True}

class FamiliarityCreate(BaseModel): # Using Pydantic BaseModel for request body
    # Using PydanticField for validation in request body model
    score: int = PydanticField(gt=0, le=5, description="Familiarity score from 1 (least) to 5 (most).")

class FamiliarityUpdate(FamiliarityCreate): # Can be the same as Create for this simple case
    pass
