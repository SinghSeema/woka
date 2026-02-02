"""Shadow Memory service for asynchronous context pre-warming and caching.

This implements the "Shadow Memory" strategy where context is pre-warmed
asynchronously during handshake and updated in the background, keeping
the critical path (User Speaking → AI Responding) fast.
"""

import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.database_service import get_past_sessions, get_past_session_embeddings
from bot.services.context_cache import ContextCache, generate_cache_key

logger = get_logger(__name__)


class ShadowMemory:
    """Manages asynchronous context pre-warming and background updates."""
    
    def __init__(self, context_cache: ContextCache, user_name: str):
        """Initialize Shadow Memory.
        
        Args:
            context_cache: ContextCache instance for storing pre-warmed data
            user_name: User's name for session-specific caching
        """
        self.context_cache = context_cache
        self.user_name = user_name
        self.prewarmed = False
        self.last_update = None
        self.cached_embeddings: List[Dict[str, Any]] = []  # Store embeddings for local search
        logger.debug(f"Initialized Shadow Memory for {user_name}")
    
    async def prewarm(
        self, 
        limit: int = 5,
        inject_into_context: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """Pre-warm cache with last N sessions asynchronously.
        
        This runs in the background during handshake, not blocking the critical path.
        
        Args:
            limit: Number of recent sessions to pre-warm (default: 5)
            inject_into_context: Optional OpenAILLMContext to inject pre-warmed sessions into
            
        Returns:
            List of pre-warmed sessions
        """
        if limit <= 0:
            logger.info(
                f"Shadow Memory pre-warm disabled (limit={limit}) for {self.user_name}"
            )
            return []

        if self.prewarmed:
            logger.debug(f"Shadow Memory already pre-warmed for {self.user_name}")
            return []
        
        try:
            logger.info(f"🔥 Pre-warming Shadow Memory for {self.user_name} (fetching last {limit} sessions)...")
            start_time = datetime.now()
            
            # OPTIMIZATION: Pre-warm embeddings first (lighter, faster)
            # Fetch only embeddings (summary + embedding vector) instead of full sessions
            logger.info(f"📥 [FLOW-STEP-1] Fetching embeddings for {self.user_name}...")
            embedding_data = await get_past_session_embeddings(self.user_name, limit=limit)
            if embedding_data:
                # Store for local similarity search
                logger.info(
                    f"💾 [FLOW-STEP-1] Storing {len(embedding_data)} embeddings in Shadow Memory "
                    f"(each has summary + embedding vector)"
                )
                for i, item in enumerate(embedding_data[:3], 1):  # Log first 3
                    summary = item.get("summary", "")
                    embedding = item.get("embedding")
                    summary_preview = summary[:100].replace("\n", " ") if summary else "N/A"
                    embedding_dim = len(embedding) if embedding else 0
                    logger.info(
                        f"   Embedding {i}: summary_len={len(summary)}, "
                        f"embedding_dim={embedding_dim}, preview='{summary_preview}...'"
                    )
                self.cached_embeddings = embedding_data
                await self._prewarm_embedding_cache(embedding_data)
                logger.info(f"✅ [FLOW-STEP-1] Embeddings stored and ready for similarity search")
            else:
                logger.warning(f"⚠️  [FLOW-STEP-1] No embeddings found for {self.user_name}")
            
            # Fetch last N sessions (non-blocking, async) for session cache
            sessions = await get_past_sessions(self.user_name, limit=limit)
            
            if sessions:
                # Cache common queries proactively
                await self._cache_common_queries(sessions)
                
                # Inject into system prompt if context provided
                if inject_into_context:
                    await self._inject_into_initial_prompt(inject_into_context, sessions)
                
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"⏱️  Shadow Memory pre-warmed: {len(sessions)} sessions cached, "
                    f"{len(embedding_data)} embeddings cached in {duration:.2f}s"
                )
            else:
                logger.debug(f"No past sessions found for {self.user_name}")
            
            self.prewarmed = True
            self.last_update = datetime.now()
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error pre-warming Shadow Memory: {e}", exc_info=True)
            return []
    
    async def _inject_into_initial_prompt(
        self,
        context: Any,
        sessions: List[Dict[str, Any]]
    ) -> None:
        """Inject pre-warmed sessions into the initial system prompt.
        
        Args:
            context: OpenAILLMContext instance
            sessions: List of sessions to inject
        """
        try:
            from bot.services.context_manager import build_past_context
            
            # Build past context string
            past_context, session_count = build_past_context(sessions, self.user_name)
            
            if not past_context:
                logger.debug("No past context to inject")
                return

            # Debug: preview what Shadow Memory is adding to the initial prompt
            preview = past_context[:600].replace("\n", " ")
            logger.debug(
                f"[shadow-memory] Built past_context for initial prompt "
                f"(sessions={session_count}, chars={len(past_context)}): {preview}"
            )
            
            # Get current messages
            messages = context.get_messages()
            if not messages:
                logger.warning("No messages in context to inject past context")
                return
            
            # Find the system message and append past context
            # Use messages[:] = pattern to ensure changes persist (same as remove_old_messages)
            updated_messages = []
            injected = False
            
            for msg in messages:
                if msg.get("role") == "system" and not injected:
                    # Append past context to existing system prompt
                    current_content = msg.get("content", "")
                    updated_content = current_content + past_context
                    updated_messages.append({
                        "role": "system",
                        "content": updated_content
                    })
                    injected = True
                    
                    logger.info(
                        f"✅ Injected {session_count} pre-warmed sessions into initial system prompt "
                        f"({len(past_context)} characters added, total system prompt: {len(updated_content)} chars)"
                    )
                else:
                    updated_messages.append(msg)
            
            # If no system message found, add one at the beginning
            if not injected:
                logger.warning("No system message found, adding new one with past context")
                updated_messages.insert(0, {
                    "role": "system",
                    "content": past_context
                })
            
            # Replace entire messages list (this pattern works for OpenAILLMContext)
            messages[:] = updated_messages
            
        except Exception as e:
            logger.error(f"Error injecting pre-warmed sessions into prompt: {e}", exc_info=True)
    
    async def _cache_common_queries(self, sessions: List[Dict[str, Any]]) -> None:
        """Cache common query patterns proactively.
        
        Args:
            sessions: List of sessions to cache
        """
        if not sessions:
            return
        
        # Cache "last session" query
        if len(sessions) >= 1:
            last_session_key = generate_cache_key(
                intent_type="general",
                query_text="last session"
            )
            self.context_cache.set(
                self.user_name,
                last_session_key,
                [sessions[0]]  # Most recent session
            )
        
        # Cache "recent sessions" query
        recent_key = generate_cache_key(
            intent_type="general",
            query_text="recent sessions"
        )
        self.context_cache.set(
            self.user_name,
            recent_key,
            sessions[:3]  # Last 3 sessions
        )
        
        # Cache "all sessions" query
        all_key = generate_cache_key(
            intent_type="general",
            query_text="all sessions"
        )
        self.context_cache.set(
            self.user_name,
            all_key,
            sessions
        )
        
        logger.debug(f"Cached {len(sessions)} sessions for common queries")
    
    async def _prewarm_embedding_cache(self, embedding_data: List[Dict[str, Any]]) -> None:
        """Pre-warm embedding cache with session summary embeddings.
        
        OPTIMIZATION: Store embeddings in embedding cache so they don't need to be
        regenerated during semantic search queries.
        
        Args:
            embedding_data: List of dicts with 'summary' and 'embedding' keys
        """
        if not embedding_data:
            return
        
        try:
            from bot.services.embedding_service import _embedding_cache
            
            if not _embedding_cache:
                logger.debug("Embedding cache not available, skipping pre-warm")
                return
            
            cached_count = 0
            for item in embedding_data:
                summary = item.get("summary", "").strip()
                embedding = item.get("embedding")
                
                if summary and embedding:
                    # Store in embedding cache (key is summary text hash)
                    _embedding_cache.set_embedding(summary, embedding)
                    cached_count += 1
            
            if cached_count > 0:
                logger.info(
                    f"✅ Pre-warmed embedding cache with {cached_count} session embeddings "
                    f"(faster semantic search)"
                )
        except Exception as e:
            logger.debug(f"Error pre-warming embedding cache (non-critical): {e}")
    
    async def update_after_response(self, current_sessions: Optional[List[Dict[str, Any]]] = None) -> None:
        """Update cache after LLM response (background, non-blocking).
        
        This compresses and updates the cache with current session state
        without blocking the response to the user.
        
        Args:
            current_sessions: Optional current sessions to update cache with
        """
        try:
            # This runs in background, don't block
            if getattr(settings, "MAX_PAST_SESSIONS", 0) <= 0:
                logger.debug(
                    f"Shadow Memory update skipped (MAX_PAST_SESSIONS<=0) for {self.user_name}"
                )
                return

            if current_sessions is None:
                # Refresh from database (lightweight query)
                current_sessions = await get_past_sessions(
                    self.user_name, limit=min(3, settings.MAX_PAST_SESSIONS)
                )
            
            if current_sessions:
                # Update common queries
                await self._cache_common_queries(current_sessions)
                self.last_update = datetime.now()
                logger.debug(f"Shadow Memory updated for {self.user_name}")
            
        except Exception as e:
            logger.debug(f"Error updating Shadow Memory (non-critical): {e}")
    
    def get_cache_hit_rate(self) -> Optional[float]:
        """Get cache hit rate if available.
        
        Returns:
            Cache hit rate (0.0-1.0) or None if not tracked
        """
        # Could implement hit rate tracking here if needed
        return None
    
    def is_prewarmed(self) -> bool:
        """Check if Shadow Memory has been pre-warmed.
        
        Returns:
            True if pre-warmed
        """
        return self.prewarmed
    
    def get_cached_embeddings(self) -> List[Dict[str, Any]]:
        """Get cached embeddings for local similarity search.
        
        Returns:
            List of dicts with 'summary' and 'embedding' keys
        """
        return self.cached_embeddings.copy()

