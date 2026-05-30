"""STT (Speech-to-Text) service wrapper.

Phase 2: pass the session language to Deepgram STT so it transcribes
non-English speech correctly.  Deepgram Nova-2 supports Hindi, Tamil,
Telugu, and many other languages natively.

TTS remains Deepgram Aura (English only) — the bot hears the user's
language but always responds in English audio.

Usage:
    stt = create_stt_service()                # English (default)
    stt = create_stt_service("hi")            # Hindi
    stt = create_stt_service("ta")            # Tamil
"""

import sys
from pathlib import Path
from typing import Optional

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from pipecat.services.deepgram.stt import DeepgramSTTService

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.language_config import (
    get_deepgram_language,
    get_display_name,
    normalise_language_code,
    DEFAULT_LANGUAGE,
)

logger = get_logger(__name__)


def create_stt_service(language_code: Optional[str] = None) -> DeepgramSTTService:
    """Create and configure the Deepgram STT service.

    Args:
        language_code: BCP-47 language code (e.g. "hi", "ta", "en").
                       Resolution order: argument → SESSION_LANGUAGE setting → "en".

    Returns:
        Configured DeepgramSTTService instance.
    """
    raw_code = (
        language_code
        or getattr(settings, "SESSION_LANGUAGE", None)
        or DEFAULT_LANGUAGE
    )
    lang_key = normalise_language_code(raw_code)
    deepgram_lang = get_deepgram_language(lang_key)
    display_name = get_display_name(lang_key)
    model = getattr(settings, "DEEPGRAM_STT_MODEL", "nova-2")

    logger.info(
        f"Creating STT service: language={display_name} ({deepgram_lang}), model={model}"
    )

    return DeepgramSTTService(
        api_key=settings.DEEPGRAM_API_KEY,
        language=deepgram_lang,
        model=model,
    )