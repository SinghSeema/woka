"""LLM service wrapper."""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from pipecat.services.groq import GroqLLMService

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_llm_service() -> GroqLLMService:
    """Create and configure LLM service.

    Returns:
        Configured GroqLLMService instance.
    """
    logger.info(f"Creating LLM service with model: {settings.LLM_MODEL}")
    return GroqLLMService(api_key=settings.GROQ_API_KEY, model=settings.LLM_MODEL)

