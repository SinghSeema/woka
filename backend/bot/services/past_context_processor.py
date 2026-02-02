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
        
        # Log initialization with settings
        logger.info(
            f"🔧 [DYNAMIC-QUERY] PastContextProcessor initialized: "
            f"user={user_name}, room={room_name}, "
            f"ENABLE_DYNAMIC_CONTEXT={settings.ENABLE_DYNAMIC_CONTEXT}, "
            f"ENABLE_SEMANTIC_SEARCH={settings.ENABLE_SEMANTIC_SEARCH}, "
            f"has_context_cache={context_cache is not None}, "
            f"has_shadow_memory={shadow_memory is not None}"
        )

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Let base class handle system frames, internal state, etc.
        await super().process_frame(frame, direction)

        frame_type = type(frame).__name__
        
        # Log ALL frames to see what's coming through (but only once per frame type to avoid spam)
        if not hasattr(self, '_logged_frame_types'):
            self._logged_frame_types = set()
        if frame_type not in self._logged_frame_types:
            logger.info(f"🔍 [DYNAMIC-QUERY] First frame of type '{frame_type}' received (direction={direction})")
            self._logged_frame_types.add(frame_type)
        
        # Check for both LLMContextFrame and OpenAILLMContextFrame (pipecat might use different types)
        is_context_frame = (
            isinstance(frame, LLMContextFrame) or 
            (OpenAILLMContextFrame and isinstance(frame, OpenAILLMContextFrame)) or
            "ContextFrame" in frame_type or 
            "LLMContext" in frame_type
        )
        
        # Log when we receive any context frame to verify it's being called
        if is_context_frame:
            logger.info(
                f"🔵 [DYNAMIC-QUERY] Received context frame! "
                f"frame_type={frame_type}, direction={direction}, is_downstream={direction == FrameDirection.DOWNSTREAM}"
            )

        # We only care about downstream LLMContextFrames (triggers for LLM).
        # All other frames are simply passed through unchanged.
        # Check for both LLMContextFrame and frame type string match
        if is_context_frame and direction == FrameDirection.DOWNSTREAM:
            logger.info(
                f"✅ [DYNAMIC-QUERY] Received context frame (DOWNSTREAM) - checking for user message..."
            )
            try:
                # Try different ways to access messages (frame structure may vary)
                messages = None
                if hasattr(frame, 'context') and hasattr(frame.context, 'get_messages'):
                    messages = frame.context.get_messages()
                elif hasattr(frame, 'messages'):
                    messages = frame.messages
                elif hasattr(frame, 'context') and hasattr(frame.context, 'messages'):
                    messages = frame.context.messages
                
                logger.info(
                    f"📋 [DYNAMIC-QUERY] Messages in context: {len(messages) if messages else 0}"
                )
                if messages:
                    # Log all message roles to debug
                    roles = [msg.get("role", "unknown") if isinstance(msg, dict) else getattr(msg, "role", "unknown") for msg in messages]
                    logger.info(f"   Message roles: {roles}")
            except Exception as e:
                logger.warning(f"⚠️  [DYNAMIC-QUERY] Error getting messages from context: {e}", exc_info=True)
                await self.push_frame(frame, direction)
                return

            if not messages:
                logger.info(f"⚠️  [DYNAMIC-QUERY] No messages in context, skipping")
                await self.push_frame(frame, direction)
                return

            # Get the last user message
            user_message = ""
            for msg in reversed(messages):
                # Handle both dict and object message formats
                if isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                else:
                    role = getattr(msg, "role", "")
                    content = getattr(msg, "content", "")
                
                logger.debug(f"   Checking message: role={role}, content_len={len(content) if content else 0}")
                if role == "user":
                    user_message = content
                    break

            if not user_message:
                logger.info(f"⚠️  [DYNAMIC-QUERY] No user message found in context messages, skipping")
                await self.push_frame(frame, direction)
                return

            logger.info(
                f"👤 [DYNAMIC-QUERY] Found user message: '{user_message[:100]}...' "
                f"(len={len(user_message)})"
            )

            # Check if we should fetch context. If dynamic context is disabled,
            # we exit immediately and never touch Supabase / embeddings.
            if not settings.ENABLE_DYNAMIC_CONTEXT:
                logger.warning(
                    f"⚠️  [DYNAMIC-QUERY] ENABLE_DYNAMIC_CONTEXT is DISABLED - skipping past context fetch"
                )
                await self.push_frame(frame, direction)
                return

            logger.info(
                f"✅ [DYNAMIC-QUERY] ENABLE_DYNAMIC_CONTEXT is enabled - processing user message..."
            )
            injected = await self._handle_fetch(user_message)
            if injected:
                logger.info(
                    f"✅ [DYNAMIC-QUERY] Context injected successfully, updating frame..."
                )
                # Update the frame with the newly injected context before pushing
                # Note: inject_past_context modifies self._context in place
                frame = LLMContextFrame(self._context)
            
            await self.push_frame(frame, direction)
        else:
            # Silently pass through non-LLMContextFrame frames (no logging to reduce noise)
            await self.push_frame(frame, direction)

    async def _handle_fetch(self, user_message: str) -> bool:
        """Detect past-reference intent, fetch context, and inject into system prompt."""

        logger.info(
            f"🔍 [DYNAMIC-QUERY] _handle_fetch called for message: '{user_message[:100]}...'"
        )

        # Prevent loops for the same exact message
        msg_hash = hash(user_message)
        if msg_hash in self._processed_queries:
            logger.debug(
                f"⏭️  [DYNAMIC-QUERY] Message already processed (hash={msg_hash}), skipping"
            )
            return False

        # 1) Detect intent – MUST be very fast and cheap.
        logger.info(f"🎯 [DYNAMIC-QUERY] Detecting past-reference intent...")
        intent = detect_past_reference_intent(user_message)
        logger.info(
            f"   Intent detection result: has_intent={intent.has_intent}, "
            f"intent_type={intent.intent_type if intent.has_intent else 'N/A'}, "
            f"query_text={intent.query_text[:50] if intent.query_text else 'N/A'}..."
        )
        
        if not intent.has_intent:
            logger.debug(
                f"⏭️  [DYNAMIC-QUERY] No past-reference intent detected - skipping context fetch"
            )
            return False

        self._processed_queries.add(msg_hash)
        logger.info(
            f"✅ [DYNAMIC-QUERY] Detected intent '{intent.intent_type}' - proceeding with context fetch"
        )

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
                    logger.info(
                        f"🔍 [DYNAMIC-QUERY] Topic intent detected with topics: {intent.topics}"
                    )
                    if settings.ENABLE_SEMANTIC_SEARCH and intent.topics:
                        logger.info(
                            f"🔍 [DYNAMIC-QUERY] Trying semantic search first for topics: {intent.topics}"
                        )
                        # OPTIMIZATION: Construct query from topics instead of full user message
                        # This improves semantic search relevance for topic queries
                        # Filter out any stop words that might have slipped through (defense in depth)
                        stop_words = {
                            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
                            'we', 'did', 'do', 'what', 'when', 'where', 'how', 'why', 'about', 'regarding', 'concerning',
                            'related', 'discuss', 'discussed', 'talk', 'talked', 'mention', 'mentioned', 'say', 'said',
                            'this', 'that', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                            'have', 'has', 'had', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must'
                        }
                        filtered_topics = [t for t in intent.topics if t.lower() not in stop_words and len(t.strip()) > 2]
                        if not filtered_topics:
                            # If all topics were filtered out, use original topics as fallback
                            filtered_topics = [t for t in intent.topics if len(t.strip()) > 2]
                        
                        # If we still have no meaningful topics, fall back to using the full query text
                        # This handles cases where topic extraction fails (e.g., "wait" instead of "zumba classes")
                        if not filtered_topics or (len(filtered_topics) == 1 and len(filtered_topics[0]) <= 4):
                            logger.warning(
                                f"⚠️  [DYNAMIC-QUERY] Topic extraction produced poor results: {filtered_topics}. "
                                f"Falling back to full query text: '{intent.query_text[:100]}...'"
                            )
                            topic_query = intent.query_text.strip()
                        else:
                            topic_query = " ".join(filtered_topics)
                            logger.info(
                                f"🔍 [DYNAMIC-QUERY] Constructed topic query for semantic search: '{topic_query}' "
                                f"(from {len(intent.topics)} topics, filtered to {len(filtered_topics)} meaningful topics)"
                            )
                        # Use higher limit for semantic search (threshold filters quality)
                        semantic_limit = getattr(settings, "MAX_SEMANTIC_SEARCH_RESULTS", 5)
                        # Use lower threshold for topic queries (0.6 vs 0.7) for better recall
                        topic_threshold = 0.6
                        logger.info(
                            f"🔍 [DYNAMIC-QUERY] Using topic-specific threshold: {topic_threshold} "
                            f"(lower than default {getattr(settings, 'SEMANTIC_SEARCH_THRESHOLD', 0.7)})"
                        )
                        sessions = await get_sessions_by_semantic_search(
                            self._user_name,
                            topic_query,  # Use topic-based query instead of intent.query_text
                            limit=semantic_limit,
                            threshold=topic_threshold,  # Lower threshold for topics
                            shadow_memory=self._shadow_memory,  # Pass for local search
                        )
                        if sessions:
                            logger.info(
                                f"✅ [DYNAMIC-QUERY] Semantic search found {len(sessions)} sessions for topics: {intent.topics}"
                            )
                        else:
                            logger.info(
                                f"⚠️  [DYNAMIC-QUERY] Semantic search found no sessions, trying keyword search..."
                            )
                    if not sessions and intent.topics:
                        logger.info(
                            f"🔍 [DYNAMIC-QUERY] Semantic search found no results, trying keyword search for topics: {intent.topics}"
                        )
                        sessions = await get_sessions_by_topic(
                            self._user_name,
                            intent.topics,
                            limit=settings.MAX_DYNAMIC_SESSIONS,
                        )
                        if sessions:
                            logger.info(
                                f"✅ [DYNAMIC-QUERY] Keyword search SUCCESS: found {len(sessions)} sessions for topics: {intent.topics}"
                            )
                        else:
                            logger.warning(
                                f"❌ [DYNAMIC-QUERY] Both semantic and keyword search found no sessions for topics: {intent.topics}"
                            )
                elif intent.intent_type == "semantic" or (
                    intent.intent_type == "general" and intent.query_text
                ):
                    if settings.ENABLE_SEMANTIC_SEARCH and intent.query_text:
                        # Use higher limit for semantic search (threshold filters quality)
                        semantic_limit = getattr(settings, "MAX_SEMANTIC_SEARCH_RESULTS", 5)
                        sessions = await get_sessions_by_semantic_search(
                            self._user_name,
                            intent.query_text,
                            limit=semantic_limit,
                            threshold=getattr(
                                settings, "SEMANTIC_SEARCH_THRESHOLD", 0.5
                            ),
                            shadow_memory=self._shadow_memory,  # Pass for local search
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
                logger.info(
                    f"📤 [FLOW-STEP-4] Passing {len(sessions)} sessions to inject_past_context "
                    f"for prompt injection..."
                )
                # Verify sessions have summary text before injection
                for i, session in enumerate(sessions, 1):
                    summary = session.get("summary", "")
                    logger.debug(
                        f"   Session {i} before injection: "
                        f"has_summary={'✅' if summary else '❌'}, "
                        f"summary_len={len(summary)}"
                    )
                success = inject_past_context(
                    self._context,
                    sessions,
                    self._user_name,
                    query_text=intent.query_text,
                )
                if success:
                    logger.info(f"✅ [FLOW-STEP-4] inject_past_context returned success=True")
                else:
                    logger.warning(f"⚠️  [FLOW-STEP-4] inject_past_context returned success=False")
                return success
        except Exception as e:
            logger.error(f"Error in PastContextProcessor fetch: {e}")

        return False

