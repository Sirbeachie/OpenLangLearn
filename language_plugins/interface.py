# Language plugin interface
from abc import ABC, abstractmethod

class LanguagePluginInterface(ABC):
    """
    Interface for language-specific processing plugins.
    Each plugin will handle tasks like subtitle parsing,
    word tokenization, lemmatization, and potentially translation
    for a specific language.
    """

    @abstractmethod
    def get_language_code(self) -> str:
        """Returns the language code supported by the plugin (e.g., 'en', 'ja')."""
        pass

    @abstractmethod
    def parse_subtitle(self, subtitle_content: str) -> list[dict]:
        """
        Parses subtitle content into a structured format.
        Each item in the list could be a dictionary with 'start_time', 'end_time', 'text'.
        """
        pass

    @abstractmethod
    def tokenize_text(self, text: str) -> list[str]:
        """Tokenizes a given text into words or morphemes."""
        pass

    @abstractmethod
    def get_word_details(self, word: str) -> dict:
        """
        Provides details for a given word.
        Could include lemma, part_of_speech, pronunciation, basic translation, etc.
        The structure of the dictionary can be flexible based on what the
        language processing tools for that language can provide.
        Example: {'lemma': '食べる', 'part_of_speech': 'verb', 'reading': 'たべる'}
        """
        pass

    @abstractmethod
    def tokenize(self, text: str) -> list[dict]:
        """
        Tokenizes a given text into a list of token information dictionaries.
        Each dictionary should contain at least 'surface', 'lemma', 'pos'.
        Example: [{'surface': '食べ', 'lemma': '食べる', 'pos': '動詞-自立'}, ...]
        """
        pass

    @abstractmethod
    def get_stop_words(self) -> set[str]:
        """
        Returns a set of stop words for the language.
        These words might be excluded from certain analyses or user interactions.
        """
        pass
