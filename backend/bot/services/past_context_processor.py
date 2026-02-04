"""Processor for dynamically injecting past context before LLM runs.

This runs on the critical path right before the LLM. It MUST:
- Exit very quickly when there is no \"past reference\" intent.
- Only hit Supabase / embeddings when clearly needed.
- Re-use the same retrieval semantics as the dynamic context handler in events.py.
"""

from datetime import datetime
from typing import Optional, Any, List, Dict

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

# Try to import OpenAILLMContextFrame if available
try:
    from pipecat.frames.frames import OpenAILLMContextFrame
except ImportError:
    OpenAILLMContextFrame = None

from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import record_context_fetch_event
from bot.services.intent_detector import detect_past_reference_intent
from bot.services.query_understanding import expand_query_for_search
from bot.services.database_service import (
    get_sessions_by_semantic_search,
    get_sessions_by_date_range,
    get_sessions_by_topic,
    get_all_sessions,
)
from bot.services.context_injector import inject_past_context
from bot.services.filler_generator import generate_filler
from bot.services.context_cache import ContextCache, generate_cache_key

logger = get_logger(__name__)

class PastContextProcessor(FrameProcessor):
    def __init__(
        self, 
        user_name: str, 
        room_name: str, 
        context: OpenAILLMContext,
        context_cache: Optional[ContextCache] = None,
        shadow_memory = None,  # Optional ShadowMemory for local embedding search
        **kwargs
    ):
        super().__init__(**kwargs)
        self._user_name = user_name
        self._room_name = room_name
        self._context = context
        self._context_cache = context_cache
        self._shadow_memory = shadow_memory
        self._processed_queries = set()
        
        logger.debug(
            f"PastContextProcessor initialized: user={user_name}, room={room_name}, "
            f"ENABLE_DYNAMIC_CONTEXT={settings.ENABLE_DYNAMIC_CONTEXT}, "
            f"ENABLE_SEMANTIC_SEARCH={settings.ENABLE_SEMANTIC_SEARCH}"
        )

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Let base class handle system frames, internal state, etc.
        await super().process_frame(frame, direction)

        frame_type = type(frame).__name__
        
        is_context_frame = (
            isinstance(frame, LLMContextFrame) or 
            (OpenAILLMContextFrame and isinstance(frame, OpenAILLMContextFrame)) or
            "ContextFrame" in frame_type or 
            "LLMContext" in frame_type
        )

        if is_context_frame and direction == FrameDirection.DOWNSTREAM:
            try:
                # Try different ways to access messages (frame structure may vary)
                messages = None
                if hasattr(frame, 'context') and hasattr(frame.context, 'get_messages'):
                    messages = frame.context.get_messages()
                elif hasattr(frame, 'messages'):
                    messages = frame.messages
                elif hasattr(frame, 'context') and hasattr(frame.context, 'messages'):
                    messages = frame.context.messages
            except Exception as e:
                logger.warning(f"Error getting messages from context: {e}", exc_info=True)
                await self.push_frame(frame, direction)
                return

            if not messages:
                await self.push_frame(frame, direction)
                return

            # Get the last user message
            user_message = ""
            for msg in reversed(messages):
                if isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                else:
                    role = getattr(msg, "role", "")
                    content = getattr(msg, "content", "")
                
                if role == "user":
                    user_message = content
                    break

            if not user_message:
                await self.push_frame(frame, direction)
                return

            if not settings.ENABLE_DYNAMIC_CONTEXT:
                await self.push_frame(frame, direction)
                return

            injected = await self._handle_fetch(user_message)
            if injected:
                # Update the frame with the newly injected context before pushing
                # Note: inject_past_context modifies self._context in place
                frame = LLMContextFrame(self._context)
            
            await self.push_frame(frame, direction)
        else:
            # Silently pass through non-LLMContextFrame frames (no logging to reduce noise)
            await self.push_frame(frame, direction)

    async def _handle_fetch(self, user_message: str) -> bool:
        """Detect past-reference intent, fetch context, and inject into system prompt."""

        # Prevent loops for the same exact message
        msg_hash = hash(user_message)
        if msg_hash in self._processed_queries:
            return False

        intent = await detect_past_reference_intent(user_message)
        
        if not intent.has_intent:
            return False

        self._processed_queries.add(msg_hash)
        logger.debug(f"Detected intent '{intent.intent_type}' for query: '{user_message[:50]}...'")

        sessions: List[Dict[str, Any]] = []

        # 2) Check Shadow Memory / ContextCache first (fast path, no DB).
        cache_key = generate_cache_key(
            intent_type=intent.intent_type,
            query_text=intent.query_text,
            date_range=intent.date_range,
            topics=intent.topics,
        )

        if self._context_cache:
            cached = self._context_cache.get(self._user_name, cache_key)
            if cached:
                logger.debug(f"Cache hit for query: {cache_key}")
                sessions = cached

        try:
            if not sessions:
                logger.debug(f"Cache miss for query: {cache_key}")

                # Send filler immediately to keep user engaged while we query DB.
                from pipecat.frames.frames import TextFrame

                filler_text = generate_filler(intent.intent_type, self._user_name)
                try:
                    await self.push_frame(TextFrame(filler_text))
                    logger.debug(f"💬 PastContextProcessor sent filler: {filler_text}")
                except Exception as e:
                    logger.debug(f"PastContextProcessor: could not send filler (non-critical): {e}")

                query_start = datetime.now()

                # Choose retrieval strategy based on intent type.
                if intent.intent_type == "date" and intent.date_range:
                    sessions = await get_sessions_by_date_range(
                        self._user_name,
                        intent.date_range["start"],
                        intent.date_range["end"],
                    )
                elif intent.intent_type == "topic" and intent.topics:
                    if settings.ENABLE_SEMANTIC_SEARCH and intent.topics:
                        # Use full original query text for semantic search (better embeddings)
                        # Topics are used for pre-filtering, not for query construction
                        filtered_topics = [t for t in intent.topics if t and len(t.strip()) > 2]
                        
                        # Use original query text for semantic search (not just topic words)
                        # This produces better embeddings for semantic similarity
                        original_query = intent.query_text.strip() if intent.query_text else " ".join(filtered_topics)
                        
                        # Expand query for better embedding quality
                        semantic_query = expand_query_for_search(original_query, intent)
                        
                        # Lower threshold for topic queries since they may have shorter queries
                        # But use full query text which should give better scores
                        semantic_limit = getattr(settings, "MAX_SEMANTIC_SEARCH_RESULTS", 5)
                        topic_threshold = 0.5  # Lower threshold for topic-based searches
                        
                        logger.debug(
                            f"Topic query: expanded '{original_query[:50]}...' → '{semantic_query[:100]}...' "
                            f"with topics {filtered_topics} for pre-filtering"
                        )
                        
                        sessions = await get_sessions_by_semantic_search(
                            self._user_name,
                            semantic_query,  # Use expanded query for better embeddings
                            limit=semantic_limit,
                            threshold=topic_threshold,
                            topics=filtered_topics,  # Pass topics for pre-filtering
                            shadow_memory=self._shadow_memory,
                        )
                    if not sessions and intent.topics:
                        sessions = await get_sessions_by_topic(
                            self._user_name,
                            intent.topics,
                            limit=settings.MAX_DYNAMIC_SESSIONS,
                        )
                elif intent.intent_type == "semantic" or (
                    intent.intent_type == "general" and intent.query_text
                ):
                    if settings.ENABLE_SEMANTIC_SEARCH and intent.query_text:
                        # Expand query for better embedding quality
                        original_query = intent.query_text.strip()
                        semantic_query = expand_query_for_search(original_query, intent)
                        
                        # Use higher limit for semantic search (threshold filters quality)
                        semantic_limit = getattr(settings, "MAX_SEMANTIC_SEARCH_RESULTS", 5)
                        logger.debug(
                            f"General/semantic query: expanded '{original_query[:50]}...' → '{semantic_query[:100]}...'"
                        )
                        sessions = await get_sessions_by_semantic_search(
                            self._user_name,
                            semantic_query,  # Use expanded query
                            limit=semantic_limit,
                            threshold=getattr(
                                settings, "SEMANTIC_SEARCH_THRESHOLD", 0.5
                            ),
                            topics=intent.topics if intent.topics else None,  # Pass topics if available
                            shadow_memory=self._shadow_memory,  # Pass for local search
                        )

                # Fallback: if user explicitly asked for history and search found 0,
                # just grab the most recent sessions anyway.
                if not sessions and intent.has_intent:
                    sessions = await get_all_sessions(
                        self._user_name, limit=settings.MAX_DYNAMIC_SESSIONS
                    )

                query_duration = (datetime.now() - query_start).total_seconds() * 1000
                logger.debug(f"Context fetch: {query_duration:.0f}ms, found {len(sessions)} sessions")

                # Record event in Langfuse (non-blocking helper).
                record_context_fetch_event(
                    user_name=self._user_name,
                    room_name=self._room_name,
                    intent_type=intent.intent_type or "unknown",
                    query_text=intent.query_text,
                    sessions_found=len(sessions),
                    duration_ms=query_duration,
                )

                # Cache results for future queries
                if self._context_cache and sessions:
                    self._context_cache.set(self._user_name, cache_key, sessions)

            # 4) Inject context if we have sessions.
            if sessions:
                success = inject_past_context(
                    self._context,
                    sessions,
                    self._user_name,
                    query_text=intent.query_text,
                )
                logger.debug(f"Injected {len(sessions)} sessions into context: success={success}")
                return success
        except Exception as e:
            logger.error(f"Error in PastContextProcessor fetch: {e}")

        return False

