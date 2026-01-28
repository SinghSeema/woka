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

from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import record_context_fetch_event
from bot.services.intent_detector import detect_past_reference_intent
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
        **kwargs
    ):
        super().__init__(**kwargs)
        self._user_name = user_name
        self._room_name = room_name
        self._context = context
        self._context_cache = context_cache
        self._processed_queries = set()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Let base class handle system frames, internal state, etc.
        await super().process_frame(frame, direction)

        # We only care about downstream LLMContextFrames (triggers for LLM).
        # All other frames are simply passed through unchanged.
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            try:
                messages = frame.context.get_messages()
            except Exception as e:
                logger.debug(f"PastContextProcessor: error getting messages from context: {e}")
                await self.push_frame(frame, direction)
                return

            if not messages:
                await self.push_frame(frame, direction)
                return

            # Get the last user message
            user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break

            if not user_message:
                await self.push_frame(frame, direction)
                return

            # Check if we should fetch context. If dynamic context is disabled,
            # we exit immediately and never touch Supabase / embeddings.
            if settings.ENABLE_DYNAMIC_CONTEXT:
                injected = await self._handle_fetch(user_message)
                if injected:
                    # Update the frame with the newly injected context before pushing
                    # Note: inject_past_context modifies self._context in place
                    frame = LLMContextFrame(self._context)
            
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _handle_fetch(self, user_message: str) -> bool:
        """Detect past-reference intent, fetch context, and inject into system prompt."""

        # Prevent loops for the same exact message
        msg_hash = hash(user_message)
        if msg_hash in self._processed_queries:
            return False

        # 1) Detect intent – MUST be very fast and cheap.
        intent = detect_past_reference_intent(user_message)
        if not intent.has_intent:
            return False

        self._processed_queries.add(msg_hash)
        logger.info(f"🎯 PastContextProcessor: Detected intent '{intent.intent_type}'")

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
                logger.info(f"✅ PastContextProcessor: cache hit for query: {cache_key}")
                sessions = cached

        # 3) Cache miss – we may need to hit Supabase. This is the ONLY slow path.
        try:
            if not sessions:
                logger.info(f"❌ PastContextProcessor: cache miss for query: {cache_key}")

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
                    if settings.ENABLE_SEMANTIC_SEARCH and intent.query_text:
                        sessions = await get_sessions_by_semantic_search(
                            self._user_name,
                            intent.query_text,
                            limit=settings.MAX_DYNAMIC_SESSIONS,
                            threshold=getattr(
                                settings, "SEMANTIC_SEARCH_THRESHOLD", 0.5
                            ),
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
                        sessions = await get_sessions_by_semantic_search(
                            self._user_name,
                            intent.query_text,
                            limit=settings.MAX_DYNAMIC_SESSIONS,
                            threshold=getattr(
                                settings, "SEMANTIC_SEARCH_THRESHOLD", 0.5
                            ),
                        )

                # Fallback: if user explicitly asked for history and search found 0,
                # just grab the most recent sessions anyway.
                if not sessions and intent.has_intent:
                    logger.info(
                        "ℹ️ PastContextProcessor: semantic search found nothing, "
                        "falling back to most recent sessions"
                    )
                    sessions = await get_all_sessions(
                        self._user_name, limit=settings.MAX_DYNAMIC_SESSIONS
                    )

                query_duration = (datetime.now() - query_start).total_seconds() * 1000
                logger.info(
                    f"⏱️  PastContextProcessor dynamic context fetch: "
                    f"{query_duration:.0f}ms, found {len(sessions)} sessions"
                )

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
                return success
        except Exception as e:
            logger.error(f"Error in PastContextProcessor fetch: {e}")

        return False

