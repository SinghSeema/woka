"""Logging configuration."""

import logging
import sys
from typing import Optional

from app.core.config import settings


def setup_logging(log_level: Optional[str] = None) -> None:
    """Configure application logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                  If None, uses environment-based default.
    """
    if log_level is None:
        # Always default to INFO to avoid noisy DEBUG logs from third-party libraries
        log_level = "INFO"

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Set specific logger levels - suppress verbose third-party logs
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
    # Default: keep LiveKit and Pipecat logs at WARNING to avoid noisy output
    logging.getLogger("livekit").setLevel(logging.WARNING)
    logging.getLogger("pipecat").setLevel(logging.WARNING)
    
    # Suppress verbose Pipecat service logs (LLM context printing, Deepgram, etc.)
    # Use CRITICAL here to aggressively silence DEBUG/INFO spam like full prompts and TTS chunks.
    for noisy_name in [
        "pipecat.services",
        "pipecat.services.openai",
        "pipecat.services.openai.base_llm",
        "pipecat.services.groq",
        "pipecat.services.deepgram",
        "pipecat.services.deepgram.stt",
        "pipecat.services.deepgram.tts",
    ]:
        noisy_logger = logging.getLogger(noisy_name)
        noisy_logger.setLevel(logging.CRITICAL)
        # Explicitly detach them from root handlers so they can't print even if misconfigured elsewhere
        noisy_logger.handlers.clear()
        noisy_logger.propagate = False
    logging.getLogger("pipecat.transports").setLevel(logging.WARNING)
    logging.getLogger("pipecat.transports.base_input").setLevel(logging.WARNING)
    logging.getLogger("pipecat.transports.base_output").setLevel(logging.WARNING)
    logging.getLogger("pipecat.pipeline").setLevel(logging.WARNING)
    logging.getLogger("pipecat.pipeline.task").setLevel(logging.WARNING)
    logging.getLogger("pipecat.audio").setLevel(logging.WARNING)
    
    # Suppress verbose HTTP/2 and networking logs
    logging.getLogger("hpack").setLevel(logging.ERROR)
    logging.getLogger("hpack.hpack").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("httpcore.http2").setLevel(logging.ERROR)
    logging.getLogger("httpcore.connection").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
    
    # Suppress other verbose libraries
    logging.getLogger("asyncio").setLevel(logging.ERROR)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("livekit.agents").setLevel(logging.WARNING)
    logging.getLogger("livekit.rtc").setLevel(logging.WARNING)
    logging.getLogger("livekit.protocol").setLevel(logging.ERROR)
    
    # Suppress sentence-transformers and Hugging Face verbose logs
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)
    logging.getLogger("transformers.configuration_utils").setLevel(logging.ERROR)
    logging.getLogger("transformers.tokenization_utils_base").setLevel(logging.ERROR)
    logging.getLogger("transformers.modeling_bert").setLevel(logging.ERROR)
    
    # Suppress filelock verbose DEBUG logs
    logging.getLogger("filelock").setLevel(logging.WARNING)
    
    # Suppress Hugging Face hub logs
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub.file_download").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub.hf_api").setLevel(logging.ERROR)
    
    # Suppress verbose bot main module logs
    logging.getLogger("__mp_main__").setLevel(logging.WARNING)
    logging.getLogger("bot.main").setLevel(logging.WARNING)
    
    # Suppress embedding / context / summary verbose logs from our own services,
    # even when the root logger is set to DEBUG for troubleshooting.
    for noisy_bot_logger in [
        "bot.services.embedding_service",
        "bot.services.context_cache",
        "bot.services.database_service",
        "bot.services.shadow_memory",
        "bot.services.summary_service",
        "bot.services.context_injector",
    ]:
        logging.getLogger(noisy_bot_logger).setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured with level: {log_level} (verbose third-party logs suppressed)")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)

