"""Memory services initialization and management."""

import sys
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.context_cache import ContextCache
from bot.services.shadow_memory import ShadowMemory
from bot.services.conversation_memory import ConversationMemory
from bot.services.performance_monitor import get_performance_monitor
from bot.services.embedding_service import set_embedding_cache

logger = get_logger(__name__)


@dataclass
class MemoryServices:
    """Container for all memory-related services.
    
    All services are optional and may be None if their respective
    feature flags are disabled.
    """
    context_cache: Optional[ContextCache] = None
    shadow_memory: Optional[ShadowMemory] = None
    memory_manager: Optional[ConversationMemory] = None
    performance_monitor: Optional[Any] = None
    
    def __post_init__(self):
        """Validate service dependencies after initialization."""
        # ShadowMemory requires ContextCache
        if self.shadow_memory and not self.context_cache:
            logger.warning(
                "ShadowMemory initialized without ContextCache - this should not happen"
            )


async def initialize_memory_services(
    user_name: str,
    room_name: str
) -> MemoryServices:
    """Initialize all memory-related services.
    
    This function handles the initialization of:
    - ContextCache (for dynamic context queries)
    - ShadowMemory (for async context pre-warming)
    - ConversationMemory (for long session management)
    - PerformanceMonitor (for metrics collection)
    
    Services are initialized based on feature flags in settings.
    Independent services can be initialized in parallel for better performance.
    
    Args:
        user_name: User's name for session-specific services
        room_name: Room/session name for performance monitoring
        
    Returns:
        MemoryServices dataclass containing all initialized services
        
    Raises:
        Exception: If critical service initialization fails
    """
    logger.info("Initializing memory services...")
    
    # Step 1: Initialize ContextCache (required for ShadowMemory)
    context_cache = None
    if settings.ENABLE_DYNAMIC_CONTEXT:
        try:
            context_cache = ContextCache(ttl_seconds=settings.CONTEXT_CACHE_TTL)
            set_embedding_cache(context_cache)
            logger.info(f"✅ Initialized context cache (TTL: {settings.CONTEXT_CACHE_TTL}s)")
        except Exception as e:
            logger.error(f"❌ Failed to initialize context cache: {e}", exc_info=True)
            # Continue without context cache (graceful degradation)
    
    # Step 2: Initialize independent services
    # These can be initialized in parallel, but since they're lightweight,
    # sequential initialization is fine and clearer
    memory_manager = None
    if getattr(settings, 'ENABLE_CONVERSATION_MEMORY', True):
        try:
            memory_manager = ConversationMemory()
            logger.info("✅ Initialized conversation memory manager")
        except Exception as e:
            logger.error(f"❌ Failed to initialize conversation memory: {e}", exc_info=True)
            # Continue without memory manager (graceful degradation)
    
    performance_monitor = None
    if getattr(settings, 'ENABLE_PERFORMANCE_MONITORING', True):
        try:
            performance_monitor = get_performance_monitor()
            performance_monitor.start_session(user_name, room_name)
            logger.info("✅ Initialized performance monitor")
        except Exception as e:
            logger.error(f"❌ Failed to initialize performance monitor: {e}", exc_info=True)
            # Continue without performance monitor (graceful degradation)
    
    # Step 3: Initialize ShadowMemory (depends on context_cache)
    shadow_memory = None
    if settings.ENABLE_DYNAMIC_CONTEXT and context_cache:
        try:
            shadow_memory = ShadowMemory(context_cache, user_name)
            logger.info("✅ Initialized Shadow Memory")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Shadow Memory: {e}", exc_info=True)
            # Continue without shadow memory (graceful degradation)
    
    logger.info("✅ Memory services initialization completed")
    
    return MemoryServices(
        context_cache=context_cache,
        shadow_memory=shadow_memory,
        memory_manager=memory_manager,
        performance_monitor=performance_monitor
    )

