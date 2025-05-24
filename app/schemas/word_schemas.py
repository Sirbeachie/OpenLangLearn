from pydantic import BaseModel, Field
from typing import List, Optional

class DefinitionEntry(BaseModel):
    gloss: str # The definition text
    part_of_speech: Optional[str] = None
    # Example: Optional[str] = None # Placeholder for example sentences

class WordDefinitionResponse(BaseModel):
    word_id: int
    lemma: str # The lemma (dictionary form) of the word
    language: str # Language code (e.g., 'ja', 'en')
    definitions: List[DefinitionEntry]

    class Config:
        # For Pydantic V1, use orm_mode = True
        # For Pydantic V2, use from_attributes = True
        # This allows the model to be populated from ORM objects directly.
        # Assuming Pydantic V1 for now based on project history.
        orm_mode = True
        # If using Pydantic V2, you would use:
        # model_config = {"from_attributes": True}
