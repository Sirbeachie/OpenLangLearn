# app/services/dictionary_service.py
import logging
from app.schemas.word_schemas import WordDefinitionResponse, DefinitionEntry
from app.models.subtitle import Word # To type hint Word object

# Import Jamdict
from jamdict import Jamdict
import asyncio # For running async example usage if needed

logger = logging.getLogger(__name__)

class DictionaryService:
    def __init__(self):
        self.jmd = None
        try:
            logger.info("Initializing Jamdict...")
            self.jmd = Jamdict()
            logger.info(f"Jamdict initialized. Data directory: {self.jmd.data_dir}")
            # You can perform a quick lookup to ensure data is available/downloaded
            # For example: self.jmd.lookup("test")
            logger.info("Jamdict ready.")
        except Exception as e:
            logger.error(f"Failed to initialize Jamdict: {e}")
            logger.error("Japanese dictionary lookups will not be available.")
            # self.jmd will remain None, and lookups for 'ja' will fail gracefully or return empty.

    async def lookup_definition(self, word: Word) -> WordDefinitionResponse:
        """
        Looks up the definition of a word.
        Uses Jamdict for Japanese, placeholder for other languages.
        """
        lemma = word.lemma
        language = word.language
        word_id = word.id

        logger.info(f"Looking up definition for lemma: '{lemma}', language: '{language}', word_id: {word_id}")

        definitions: list[DefinitionEntry] = []

        if language.lower() in ["ja", "jpn"]:
            if self.jmd is None:
                logger.warning(f"Jamdict not initialized. Cannot provide definitions for Japanese word_id: {word_id} ('{lemma}').")
                definitions.append(
                    DefinitionEntry(gloss=f"Jamdict not available for {lemma} (ID: {word_id})")
                )
            else:
                try:
                    # Jamdict's lookup is synchronous.
                    # If this service method needs to be truly async for other reasons,
                    # Jamdict lookups would need to be run in a thread pool executor.
                    # For now, assuming it's okay to call synchronous code here.
                    logger.debug(f"Performing Jamdict lookup for: '{lemma}' (word_id: {word_id})")
                    results = self.jmd.lookup(lemma, strict_lookup=True) # Using strict_lookup as per plan
                    
                    if not results or not results.entries:
                        logger.info(f"No Jamdict entries found for '{lemma}' (word_id: {word_id}).")
                        definitions.append(
                            DefinitionEntry(gloss=f"No specific definition found for {lemma} (ID: {word_id}) in Jamdict.")
                        )
                    else:
                        logger.info(f"Found {len(results.entries)} Jamdict entries for '{lemma}' (word_id: {word_id}). Processing senses.")
                        senses_processed_count = 0
                        MAX_SENSES_TO_RETURN = 5 # Limit number of senses to keep response manageable

                        for entry in results.entries:
                            if senses_processed_count >= MAX_SENSES_TO_RETURN:
                                break
                            for sense_idx, sense in enumerate(entry.senses):
                                if senses_processed_count >= MAX_SENSES_TO_RETURN:
                                    break
                                
                                gloss_texts = [str(g) for g in sense.gloss] # Get all glosses for the sense
                                gloss_text = "; ".join(gloss_texts) if gloss_texts else "No gloss available."
                                
                                pos_texts = [str(p) for p in sense.pos] # Part of speech info
                                pos_text = ", ".join(pos_texts) if pos_texts else None

                                definitions.append(
                                    DefinitionEntry(
                                        gloss=gloss_text,
                                        part_of_speech=pos_text
                                    )
                                )
                                senses_processed_count += 1
                                logger.debug(f"Added sense {sense_idx+1} from entry for '{lemma}'. Total senses: {senses_processed_count}")
                        
                        if not definitions: # Should not happen if results.entries was populated, but as a fallback
                             definitions.append(
                                DefinitionEntry(gloss=f"No processable senses found for {lemma} (ID: {word_id}) in Jamdict.")
                            )

                except Exception as e_jamdict:
                    logger.error(f"Error during Jamdict lookup for '{lemma}' (word_id: {word_id}): {e_jamdict}")
                    definitions.append(
                        DefinitionEntry(gloss=f"Error looking up definition for {lemma} (ID: {word_id}).")
                    )
        
        elif language.lower() in ["en", "eng"]: # Keep placeholder for English
            definitions.append(
                DefinitionEntry(
                    gloss=f"Placeholder English definition for {lemma} (ID: {word_id})",
                    part_of_speech="noun"
                )
            )
        else: # Placeholder for other languages
            definitions.append(
                DefinitionEntry(
                    gloss=f"No dictionary support for language '{language}' for word {lemma} (ID: {word_id})"
                )
            )
        
        return WordDefinitionResponse(
            word_id=word_id,
            lemma=lemma,
            language=language,
            definitions=definitions
        )

# Example usage (for direct testing of this service)
async def main_test():
    # This requires the Word model to be instantiable for testing
    # from app.models.subtitle import Word 
    service = DictionaryService()
    
    if service.jmd: # Only test Japanese if Jamdict initialized
        print("\n--- Testing Japanese ---")
        jp_word1 = Word(id=1, lemma="食べる", language="ja")
        jp_def1 = await service.lookup_definition(jp_word1)
        print(jp_def1.json(indent=2, ensure_ascii=False))

        jp_word2 = Word(id=2, lemma="学校", language="jpn")
        jp_def2 = await service.lookup_definition(jp_word2)
        print(jp_def2.json(indent=2, ensure_ascii=False))
        
        jp_word3 = Word(id=3, lemma="存在しない言葉", language="ja") # Non-existent word
        jp_def3 = await service.lookup_definition(jp_word3)
        print(jp_def3.json(indent=2, ensure_ascii=False))

    print("\n--- Testing English (Placeholder) ---")
    en_word = Word(id=4, lemma="test", language="en")
    en_def = await service.lookup_definition(en_word)
    print(en_def.json(indent=2))

    print("\n--- Testing Unknown Language (Placeholder) ---")
    xx_word = Word(id=5, lemma="glorp", language="xx")
    xx_def = await service.lookup_definition(xx_word)
    print(xx_def.json(indent=2))

if __name__ == "__main__":
    # Setup basic logging for testing
    logging.basicConfig(level=logging.INFO)
    # To run the async main_test function
    asyncio.run(main_test())
