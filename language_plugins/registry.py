# Language Plugin Registry
from typing import Dict, Type, Optional

from .interface import LanguagePluginInterface
from .japanese.plugin import JapanesePlugin
# Import other plugins here as they are created
# from .english.plugin import EnglishPlugin # Example

# The registry maps language codes (lowercase) to plugin classes.
LANGUAGE_PLUGINS: Dict[str, Type[LanguagePluginInterface]] = {
    "ja": JapanesePlugin,  # Using ISO 639-1 code for Japanese
    "jpn": JapanesePlugin, # ISO 639-3 code, alias for Japanese
    # "en": EnglishPlugin, # Example for future English plugin
    # "eng": EnglishPlugin, # Alias for English
}

def get_language_plugin(language_code: str) -> Optional[LanguagePluginInterface]:
    """
    Retrieves an initialized language plugin instance based on the language code.

    Args:
        language_code: The language code (e.g., "ja", "en"). Case-insensitive.

    Returns:
        An instance of the language plugin if found, otherwise None.
    """
    if not language_code:
        return None
        
    plugin_class = LANGUAGE_PLUGINS.get(language_code.lower())
    if plugin_class:
        try:
            return plugin_class() # Instantiate the plugin
        except Exception as e:
            # Log the error during plugin instantiation
            # Consider using a proper logger here if available globally
            print(f"Error instantiating plugin for language '{language_code}': {e}")
            return None
    return None

# Example usage (can be removed or kept for direct testing of the registry)
if __name__ == "__main__":
    # Test Japanese plugin
    jp_plugin = get_language_plugin("ja")
    if jp_plugin:
        print(f"Japanese plugin loaded. Language code: {jp_plugin.get_language_code()}")
        tokens = jp_plugin.tokenize("これはテストです。")
        print(f"Tokens for 'これはテストです。': {tokens}")
    else:
        print("Japanese plugin not found.")

    # Test a non-existent plugin
    non_existent_plugin = get_language_plugin("xx")
    if non_existent_plugin:
        print("Non-existent plugin loaded (this should not happen).")
    else:
        print("Non-existent plugin correctly not found.")

    # Test English plugin (assuming it's commented out or not yet implemented)
    # en_plugin = get_language_plugin("en")
    # if en_plugin:
    #     print(f"English plugin loaded. Language code: {en_plugin.get_language_code()}")
    # else:
    #     print("English plugin not found (as expected if not implemented/registered).")
