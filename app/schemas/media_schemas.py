# app/schemas/media_schemas.py
from pydantic import BaseModel, HttpUrl

class MediaURLResponse(BaseModel):
    url: HttpUrl # Using HttpUrl for validation

class MediaUploadResponse(BaseModel): # Placeholder if needed for upload, not directly for this task
    id: int
    title: str
    source_path: str # This would be the S3 key

    class Config:
        orm_mode = True # For Pydantic V1
        # For Pydantic V2, use: model_config = {"from_attributes": True}
