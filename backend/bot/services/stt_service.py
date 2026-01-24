"""STT (Speech-to-Text) service wrapper."""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from pipecat.services.deepgram import DeepgramSTTService

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_stt_service() -> DeepgramSTTService:
    """Create and configure STT service.

    Returns:
        Configured DeepgramSTTService instance.
    """
    logger.info("Creating STT service")
    return DeepgramSTTService(api_key=settings.DEEPGRAM_API_KEY)

