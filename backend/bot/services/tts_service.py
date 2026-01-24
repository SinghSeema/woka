"""TTS (Text-to-Speech) service wrapper."""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from pipecat.services.cartesia import CartesiaTTSService

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_tts_service() -> CartesiaTTSService:
    """Create and configure TTS service.

    Returns:
        Configured CartesiaTTSService instance.
    """
    logger.info(f"Creating TTS service with voice ID: {settings.CARTESIA_VOICE_ID}")
    return CartesiaTTSService(
        api_key=settings.CARTESIA_API_KEY, voice_id=settings.CARTESIA_VOICE_ID
    )

