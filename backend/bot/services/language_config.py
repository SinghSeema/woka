"""Language configuration for multilingual support.

Woka uses Deepgram for both STT and TTS:
  - STT: Deepgram Nova-2 supports Hindi, Tamil, Telugu, Bengali, and many others.
  - TTS: Deepgram Aura is English-only. Non-English sessions are transcribed
         in the user's language but the bot responds in English audio.

This is the single source of truth for:
  - Which languages Deepgram STT supports (and their exact API codes)
  - Human-readable names for logging and the system prompt

Adding a new language: just add one row to SUPPORTED_LANGUAGES.
Verify the language code at: https://developers.deepgram.com/docs/languages
"""

from typing import Optional, Tuple

# ─── Language table ───────────────────────────────────────────────────────────
#
# Key   : normalised BCP-47 code (lowercase), as passed from frontend or .env
# Value : (deepgram_stt_code, display_name)
#
SUPPORTED_LANGUAGES: dict[str, Tuple[str, str]] = {
    # English variants
    "en":    ("en",    "English"),
    "en-us": ("en-US", "English (US)"),
    "en-in": ("en-IN", "English (India)"),
    "en-gb": ("en-GB", "English (UK)"),
    "en-au": ("en-AU", "English (AU)"),

    # Indian languages
    "hi":    ("hi",    "Hindi"),
    "ta":    ("ta",    "Tamil"),
    "te":    ("te",    "Telugu"),
    "bn":    ("bn",    "Bengali"),
    "mr":    ("mr",    "Marathi"),
    "kn":    ("kn",    "Kannada"),
    "gu":    ("gu",    "Gujarati"),
    "ml":    ("ml",    "Malayalam"),
    "pa":    ("pa",    "Punjabi"),

    # Other world languages
    "es":    ("es",    "Spanish"),
    "fr":    ("fr",    "French"),
    "de":    ("de",    "German"),
    "pt":    ("pt",    "Portuguese"),
    "ar":    ("ar",    "Arabic"),
    "ja":    ("ja",    "Japanese"),
    "ko":    ("ko",    "Korean"),
    "zh":    ("zh",    "Chinese (Mandarin)"),
    "ru":    ("ru",    "Russian"),
    "it":    ("it",    "Italian"),
    "nl":    ("nl",    "Dutch"),
    "tr":    ("tr",    "Turkish"),
    "pl":    ("pl",    "Polish"),
    "sv":    ("sv",    "Swedish"),
    "id":    ("id",    "Indonesian"),
}

DEFAULT_LANGUAGE = "en"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def normalise_language_code(code: str) -> str:
    """Lowercase and strip so 'Hi', 'HI', 'hi' all resolve correctly."""
    return code.strip().lower()


def is_supported(language_code: str) -> bool:
    """True if the language code is in SUPPORTED_LANGUAGES."""
    return normalise_language_code(language_code) in SUPPORTED_LANGUAGES


def get_language_config(language_code: str) -> Tuple[str, str]:
    """Return (deepgram_stt_code, display_name).

    Falls back to English if the code is unknown.
    Tries prefix match: 'en-sg' → 'en' if 'en-sg' not explicit.
    """
    key = normalise_language_code(language_code)
    if key in SUPPORTED_LANGUAGES:
        return SUPPORTED_LANGUAGES[key]
    # Prefix match
    prefix = key.split("-")[0]
    if prefix in SUPPORTED_LANGUAGES:
        return SUPPORTED_LANGUAGES[prefix]
    # Unknown → English fallback
    return SUPPORTED_LANGUAGES[DEFAULT_LANGUAGE]


def get_deepgram_language(language_code: str) -> str:
    """Return the Deepgram STT API language code."""
    deepgram_code, _ = get_language_config(language_code)
    return deepgram_code


def get_display_name(language_code: str) -> str:
    """Return a human-readable name for the language."""
    _, name = get_language_config(language_code)
    return name


def is_english(language_code: str) -> bool:
    """True if the language is an English variant (or an unrecognised code that falls back to English)."""
    key = normalise_language_code(language_code)
    if key.startswith("en"):
        return True
    # Unknown codes fall back to English in get_language_config
    if key not in SUPPORTED_LANGUAGES and key.split("-")[0] not in SUPPORTED_LANGUAGES:
        return True  # fallback path → English
    return False