# Japanese language plugin
from language_plugins.interface import LanguagePluginInterface
from sudachipy import Dictionary, SplitMode
import logging

logger = logging.getLogger(__name__)

class JapanesePlugin(LanguagePluginInterface):
    """
    Japanese language processing plugin using SudachiPy.
    """

    def __init__(self):
        try:
            self.tokenizer = Dictionary().create()
            logger.info("SudachiPy Japanese tokenizer initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize SudachiPy tokenizer: {e}")
            self.tokenizer = None
        # Common Japanese stop words (particles, auxiliary verbs, etc.)
        # This list can be expanded.
        self._stop_words = {
            "の", "に", "は", "を", "た", "だ", "て", "で", "ます", "です", "ある", "いる", "する", "ない",
            "これ", "それ", "あれ", "どれ", "この", "その", "あの", "どの", "ここ", "そこ", "あそこ", "どこ",
            "から", "まで", "より", "ほど", "など", "くらい", "ばかり", "だけ", "しか", "さえ", "こそ",
            "が", "も", "へ", "と", "や", "とか", "やら", "なり", "やら",
            "。", "、", "「", "」", "（", "）", "？", "！", " ", "　" # Punctuation and spaces
        }


    def get_language_code(self) -> str:
        return "ja" # Using 'ja' as per ISO 639-1, though 'jpn' was in task description. Sticking to 'ja'.

    def parse_subtitle(self, subtitle_content: str) -> list[dict]:
        """
        Parses Japanese subtitle content.
        This might involve handling specific formats or encodings.
        For now, a simple split by lines, assuming each line is a subtitle entry.
        A more robust parser would handle timing information (e.g., from .srt or .vtt).
        This method is less relevant now with Whisper providing timed segments.
        """
        lines = subtitle_content.strip().split('\n')
        parsed_subtitles = []
        for i, line_text in enumerate(lines):
            parsed_subtitles.append({
                "id": i, 
                "start_time": "00:00:00,000", # Placeholder
                "end_time": "00:00:00,000",   # Placeholder
                "text": line_text.strip()
            })
        return parsed_subtitles

    def tokenize(self, text: str) -> list[dict]:
        """
        Tokenizes Japanese text using SudachiPy.
        Returns a list of dictionaries, each containing 'surface', 'lemma', and 'pos'.
        """
        if not self.tokenizer:
            logger.error("SudachiPy tokenizer not initialized. Cannot tokenize.")
            # Fallback to basic splitting or return empty list
            return [{"surface": word, "lemma": word, "pos": "UNKNOWN"} for word in text.split()]

        tokens = []
        # Using Mode.C for more detailed segmentation suitable for NLP tasks
        for m in self.tokenizer.tokenize(text, SplitMode.C):
            tokens.append({
                "surface": m.surface(),
                "lemma": m.dictionary_form(),
                "pos": "-".join(m.part_of_speech()), # POS tags are a list, join them
            })
        return tokens
    
    def get_word_details(self, word: str) -> dict:
        """
        Provides details for a single Japanese word using SudachiPy.
        This might be less used if `tokenize` provides sufficient detail.
        """
        if not self.tokenizer:
            logger.warning("SudachiPy tokenizer not initialized. Cannot get word details.")
            return {"word": word, "lemma": word, "part_of_speech": "unknown", "reading": ""}

        # Tokenize the word (it might be a phrase or compound)
        morphemes = self.tokenizer.tokenize(word, SplitMode.C)
        if not morphemes:
            return {"word": word, "lemma": word, "part_of_speech": "unknown", "reading": ""}
        
        # For simplicity, returning details of the first morpheme if multiple
        m = morphemes[0] 
        return {
            "word": word, # The input word
            "surface": m.surface(), # Surface of the first token
            "lemma": m.dictionary_form(),
            "part_of_speech": "-".join(m.part_of_speech()),
            "reading": m.reading_form() # Reading of the token
        }

    def get_stop_words(self) -> set[str]:
        """
        Returns a set of common Japanese stop words.
        """
        return self._stop_words

# Example usage (for testing the plugin directly)
if __name__ == '__main__':
    plugin = JapanesePlugin()
    if plugin.tokenizer:
        print(f"Plugin for language: {plugin.get_language_code()}")

        sample_text = "これは美しいペンです。"
        print(f"\nTokenizing text: '{sample_text}'")
        tokens = plugin.tokenize(sample_text)
        for token in tokens:
            print(token)

        print(f"\nStop words: {plugin.get_stop_words()}")

        print("\nGetting details for '食べる':") # Example of get_word_details
        details = plugin.get_word_details("食べる")
        print(details)
        
        print("\nGetting details for '食べました':") # Example of get_word_details
        details_tabemashita = plugin.get_word_details("食べました")
        print(details_tabemashita)
    else:
        print("Failed to initialize Japanese plugin.")
