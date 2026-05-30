"""TTS (Text-to-Speech) service wrapper.

Deepgram Aura TTS is English-only. This service is unchanged from Phase 1 —
we always use Deepgram Aura regardless of session language.

The multilingual story for TTS:
  - User speaks Hindi → Deepgram STT transcribes it correctly
  - LLM receives Hindi text → responds in English (or bilingual, see prompt_builder)
  - Deepgram Aura speaks English → user hears English audio

This means no change to tts_service.py for Phase 2. This file is kept
in the Phase 2 deliverable purely for completeness / documentation.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from pipecat.services.deepgram.tts import DeepgramTTSService

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_tts_service() -> DeepgramTTSService:
    """Create and configure the Deepgram TTS service.

    Always uses Deepgram Aura (English). For non-English sessions the LLM
    responds in English so Aura can speak it naturally.

    Returns:
        Configured DeepgramTTSService instance.
    """
    logger.info(f"Creating Deepgram TTS service: voice={settings.DEEPGRAM_TTS_VOICE}")
    return DeepgramTTSService(
        api_key=settings.DEEPGRAM_API_KEY,
        voice=settings.DEEPGRAM_TTS_VOICE,
    )