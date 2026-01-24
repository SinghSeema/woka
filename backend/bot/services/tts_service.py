"""TTS (Text-to-Speech) service wrapper."""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from pipecat.services.deepgram import DeepgramTTSService

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_tts_service() -> DeepgramTTSService:
    """Create and configure TTS service.

    Returns:
        Configured DeepgramTTSService instance.
    """
    logger.info(f"Creating Deepgram TTS service with voice: {settings.DEEPGRAM_TTS_VOICE}")
    return DeepgramTTSService(
        api_key=settings.DEEPGRAM_API_KEY,
        voice=settings.DEEPGRAM_TTS_VOICE,
    )

