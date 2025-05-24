# app/api/words_api.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
import logging

from app.schemas.word_schemas import WordDefinitionResponse
from app.models.subtitle import Word # Assuming Word model is in subtitle.py
from app.models.user import User
from app.core.users import current_active_user
from app.services.dictionary_service import DictionaryService

# This will be properly set up in main.py by overriding this placeholder
# with the actual get_db_session from main.py's scope.
async def get_db_session() -> Session:
    pass 

router = APIRouter()
logger = logging.getLogger(__name__)

# app/api/words_api.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
import logging

from app.schemas.word_schemas import WordDefinitionResponse
from app.schemas.familiarity_schemas import FamiliarityRead, FamiliarityCreate # New schemas
from app.models.subtitle import Word 
from app.models.user import User
from app.core.users import current_active_user
from app.services.dictionary_service import DictionaryService
from app.services.familiarity_service import FamiliarityService # New service

# This will be properly set up in main.py by overriding this placeholder
# with the actual get_db_session from main.py's scope.
async def get_db_session() -> Session:
    pass 

router = APIRouter()
logger = logging.getLogger(__name__)

# Dependency for DictionaryService
def get_dictionary_service():
    return DictionaryService()

# Dependency for FamiliarityService
def get_familiarity_service():
    return FamiliarityService()

@router.get(
    "/words/{word_id}/lookup", 
    response_model=WordDefinitionResponse,
    summary="Lookup Word Definition",
    description="Retrieves a placeholder definition for a given word ID."
)
async def lookup_word_definition(
    word_id: int,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(current_active_user), 
    dictionary_service: DictionaryService = Depends(get_dictionary_service)
):
    logger.info(f"User {current_user.id} looking up definition for word_id: {word_id}")
    if not db:
        logger.error(f"DB session not available for lookup (word_id: {word_id}, user: {current_user.id}).")
        raise HTTPException(status_code=500, detail="Database not configured")
    db_word = db.get(Word, word_id)
    if not db_word:
        logger.warning(f"Word with id: {word_id} not found (user: {current_user.id}).")
        raise HTTPException(status_code=404, detail=f"Word with id {word_id} not found")
    definition_response = await dictionary_service.lookup_definition(word=db_word)
    if not definition_response.definitions or \
       (definition_response.definitions[0].gloss.startswith("No definition available") and len(definition_response.definitions) == 1) :
        logger.info(f"No specific definition for word_id: {word_id} (lemma: {db_word.lemma}, lang: {db_word.language}).")
    else:
        logger.info(f"Retrieved definition for word_id: {word_id} (lemma: {db_word.lemma}) for user: {current_user.id}")
    return definition_response


@router.get(
    "/words/{word_id}/familiarity",
    response_model=FamiliarityRead,
    summary="Get Word Familiarity",
    description="Retrieves the familiarity score for a word for the current user."
)
async def get_word_familiarity(
    word_id: int,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(current_active_user),
    familiarity_service: FamiliarityService = Depends(get_familiarity_service)
):
    logger.info(f"User {current_user.id} fetching familiarity for word_id: {word_id}")
    if not db:
        logger.error(f"DB session not available for get_familiarity (word_id: {word_id}, user: {current_user.id}).")
        raise HTTPException(status_code=500, detail="Database not configured")

    # Check if word exists first
    db_word = db.get(Word, word_id)
    if not db_word:
        logger.warning(f"Word with id: {word_id} not found when fetching familiarity (user: {current_user.id}).")
        raise HTTPException(status_code=404, detail=f"Word with id {word_id} not found")

    familiarity = familiarity_service.get_familiarity(db, user_id=current_user.id, word_id=word_id)
    if not familiarity:
        logger.info(f"No familiarity record for word_id: {word_id}, user: {current_user.id}. Returning 404.")
        raise HTTPException(status_code=404, detail="Familiarity score not set for this word.")
    
    logger.info(f"Retrieved familiarity for word_id: {word_id}, user: {current_user.id}, score: {familiarity.score}")
    return familiarity


@router.post(
    "/words/{word_id}/familiarity",
    response_model=FamiliarityRead,
    summary="Set Word Familiarity",
    description="Sets or updates the familiarity score for a word for the current user."
)
async def set_word_familiarity(
    word_id: int,
    familiarity_in: FamiliarityCreate,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(current_active_user),
    familiarity_service: FamiliarityService = Depends(get_familiarity_service)
):
    logger.info(f"User {current_user.id} setting familiarity for word_id: {word_id} with score: {familiarity_in.score}")
    if not db:
        logger.error(f"DB session not available for set_familiarity (word_id: {word_id}, user: {current_user.id}).")
        raise HTTPException(status_code=500, detail="Database not configured")

    # Service method `upsert_familiarity` already checks if Word exists.
    updated_familiarity = familiarity_service.upsert_familiarity(
        db, user_id=current_user.id, word_id=word_id, score=familiarity_in.score
    )

    if not updated_familiarity:
        # This case implies the word_id was invalid as per service logic.
        logger.warning(f"Failed to set familiarity for word_id: {word_id} (user: {current_user.id}) - word may not exist.")
        raise HTTPException(status_code=404, detail=f"Word with id {word_id} not found, cannot set familiarity.")
        
    logger.info(f"Successfully set familiarity for word_id: {word_id}, user: {current_user.id}. New score: {updated_familiarity.score}")
    return updated_familiarity


from typing import List # Import List for response model

@router.post(
    "/words/batch-familiarity",
    response_model=List[FamiliarityRead],
    summary="Get Batch Word Familiarity",
    description="Retrieves familiarity scores for a list of words for the current user."
)
async def get_batch_word_familiarity(
    request_data: BatchFamiliarityRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(current_active_user),
    familiarity_service: FamiliarityService = Depends(get_familiarity_service)
):
    logger.info(f"User {current_user.id} fetching batch familiarity for {len(request_data.word_ids)} word_ids.")
    if not db:
        logger.error(f"DB session not available for batch_familiarity (user: {current_user.id}).")
        raise HTTPException(status_code=500, detail="Database not configured")

    if not request_data.word_ids:
        logger.info(f"User {current_user.id} requested batch familiarity with an empty list of word_ids.")
        return [] # Return empty list if no word_ids are provided

    familiarity_records = familiarity_service.get_batch_familiarity(
        db, user_id=current_user.id, word_ids=request_data.word_ids
    )
    
    logger.info(f"Retrieved {len(familiarity_records)} familiarity records for user: {current_user.id} for {len(request_data.word_ids)} requested word_ids.")
    # FastAPI will automatically convert List[Familiarity] to List[FamiliarityRead]
    return familiarity_records
