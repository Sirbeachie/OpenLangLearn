# app/services/familiarity_service.py
from sqlmodel import Session, select
from datetime import datetime
import logging

from app.models.familiarity import Familiarity
from app.models.subtitle import Word # To check if the word exists

logger = logging.getLogger(__name__)

class FamiliarityService:
    def get_familiarity(self, db: Session, user_id: int, word_id: int) -> Familiarity | None:
        """
        Retrieves a single Familiarity record for the given user_id and word_id.
        """
        logger.info(f"Fetching familiarity for user_id: {user_id}, word_id: {word_id}")
        # Familiarity has a composite primary key, so get by tuple or individual fields
        familiarity_record = db.exec(
            select(Familiarity).where(Familiarity.user_id == user_id, Familiarity.word_id == word_id)
        ).first()
        
        if familiarity_record:
            logger.info(f"Found familiarity record for user_id: {user_id}, word_id: {word_id} with score: {familiarity_record.score}")
        else:
            logger.info(f"No familiarity record found for user_id: {user_id}, word_id: {word_id}")
        return familiarity_record

    def upsert_familiarity(self, db: Session, user_id: int, word_id: int, score: int) -> Familiarity | None:
        """
        Creates a new Familiarity record or updates an existing one.
        Returns the Familiarity object or None if the word_id is invalid.
        """
        logger.info(f"Upserting familiarity for user_id: {user_id}, word_id: {word_id} with score: {score}")

        # Optional: Check if the word actually exists
        word_record = db.get(Word, word_id)
        if not word_record:
            logger.warning(f"Word with id {word_id} does not exist. Cannot set familiarity.")
            return None # Or raise HTTPException(404, "Word not found") from API layer

        familiarity_record = self.get_familiarity(db, user_id=user_id, word_id=word_id)

        if familiarity_record:
            logger.info(f"Updating existing familiarity record for user_id: {user_id}, word_id: {word_id}")
            familiarity_record.score = score
            familiarity_record.updated_at = datetime.utcnow() # Manually update timestamp
        else:
            logger.info(f"Creating new familiarity record for user_id: {user_id}, word_id: {word_id}")
            familiarity_record = Familiarity(
                user_id=user_id,
                word_id=word_id,
                score=score
                # updated_at will be set by default_factory on creation
            )
        
        db.add(familiarity_record)
        db.commit()
        db.refresh(familiarity_record)
        
        logger.info(f"Successfully upserted familiarity for user_id: {user_id}, word_id: {word_id}. New score: {familiarity_record.score}")
        return familiarity_record

    def get_batch_familiarity(self, db: Session, user_id: int, word_ids: list[int]) -> list[Familiarity]:
        """
        Retrieves multiple Familiarity records for the given user_id and a list of word_ids.
        """
        if not word_ids: # Handle empty list of word_ids if necessary
            return []
            
        logger.info(f"Fetching batch familiarity for user_id: {user_id}, word_ids: {word_ids}")
        
        familiarity_records = db.exec(
            select(Familiarity).where(
                Familiarity.user_id == user_id,
                Familiarity.word_id.in_(word_ids) # Use .in_() for list membership
            )
        ).all()
        
        logger.info(f"Found {len(familiarity_records)} familiarity records for user_id: {user_id} out of {len(word_ids)} requested word_ids.")
        return list(familiarity_records) # Ensure it's a list
