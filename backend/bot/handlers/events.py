"""Bot event handlers."""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.summary_service import generate_session_summary
from bot.services.database_service import (
    save_session_summary, check_session_exists,
    get_sessions_by_semantic_search, get_sessions_by_date_range,
    get_sessions_by_topic, get_all_sessions
)
from bot.services.intent_detector import detect_past_reference_intent
from bot.services.context_injector import inject_past_context
from bot.services.context_cache import ContextCache, generate_cache_key
from datetime import datetime

if TYPE_CHECKING:
    from pipecat.pipeline.task import PipelineTask
    from bot.services.transcript_storage import TranscriptStorage
    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

logger = get_logger(__name__)


async def setup_event_handlers(
    transport,
    task: "PipelineTask",
    transcript_storage: "TranscriptStorage",
    user_name: str,
    room_name: str,
    context: "OpenAILLMContext",
    context_cache: ContextCache = None,
) -> None:
    """Setup event handlers for transport.

    Args:
        transport: LiveKit transport instance.
        task: Pipeline task instance.
        transcript_storage: Transcript storage instance.
        user_name: User's display name.
        room_name: Room name.
        context: LLM context for accessing messages.
        context_cache: Optional context cache for dynamic queries.
    """
    from pipecat.frames.frames import LLMMessagesFrame
    
    async def handle_past_reference_query(user_message: str) -> bool:
        """Handle past reference queries by detecting intent and retrieving context.
        
        Args:
            user_message: User's message text
            
        Returns:
            True if context was injected, False otherwise
        """
        if not settings.ENABLE_DYNAMIC_CONTEXT or not settings.INTENT_DETECTION_ENABLED:
            return False
        
        try:
            # Detect intent
            intent = detect_past_reference_intent(user_message)
            
            if not intent.has_intent:
                return False
            
            logger.info(f"🔍 Detected past reference intent: {intent.intent_type} (confidence: {intent.confidence:.2f})")
            
            # Generate cache key
            cache_key = generate_cache_key(
                intent_type=intent.intent_type,
                query_text=intent.query_text,
                date_range=intent.date_range,
                topics=intent.topics
            )
            
            # Check cache first
            cached_sessions = None
            if context_cache:
                cached_sessions = context_cache.get(user_name, cache_key)
            
            if cached_sessions:
                logger.info(f"✅ Cache hit for query: {cache_key}")
                sessions = cached_sessions
            else:
                # Query database based on intent type
                sessions = []
                query_start = datetime.now()
                
                if intent.intent_type == 'date' and intent.date_range:
                    # Date-based query
                    logger.info(f"📅 Querying sessions by date range")
                    sessions = await get_sessions_by_date_range(
                        user_name,
                        intent.date_range['start'],
                        intent.date_range['end']
                    )
                elif intent.intent_type == 'topic' and intent.topics:
                    # Topic-based query (try semantic first, fallback to keyword)
                    logger.info(f"🔎 Querying sessions by topic: {', '.join(intent.topics)}")
                    if settings.ENABLE_SEMANTIC_SEARCH and intent.query_text:
                        sessions = await get_sessions_by_semantic_search(
                            user_name,
                            intent.query_text,
                            limit=settings.MAX_DYNAMIC_SESSIONS,
                            threshold=settings.SEMANTIC_SEARCH_THRESHOLD
                        )
                    
                    # Fallback to keyword search if semantic search returned no results
                    if not sessions and intent.topics:
                        logger.info("Falling back to keyword search")
                        sessions = await get_sessions_by_topic(
                            user_name,
                            intent.topics,
                            limit=settings.MAX_DYNAMIC_SESSIONS
                        )
                elif intent.intent_type == 'semantic' or (intent.intent_type == 'general' and intent.query_text):
                    # Semantic search for general queries
                    if settings.ENABLE_SEMANTIC_SEARCH and intent.query_text:
                        logger.info(f"🧠 Querying sessions by semantic search: {intent.query_text[:50]}...")
                        sessions = await get_sessions_by_semantic_search(
                            user_name,
                            intent.query_text,
                            limit=settings.MAX_DYNAMIC_SESSIONS,
                            threshold=settings.SEMANTIC_SEARCH_THRESHOLD
                        )
                    
                    # Fallback to keyword search if semantic search failed
                    if not sessions and intent.topics:
                        logger.info("Falling back to keyword search")
                        sessions = await get_sessions_by_topic(
                            user_name,
                            intent.topics,
                            limit=settings.MAX_DYNAMIC_SESSIONS
                        )
                else:
                    # General query - get all sessions
                    logger.info("📚 Querying all sessions")
                    sessions = await get_all_sessions(
                        user_name,
                        limit=settings.MAX_DYNAMIC_SESSIONS
                    )
                
                query_duration = (datetime.now() - query_start).total_seconds()
                logger.info(f"⏱️  Query completed in {query_duration:.2f}s, found {len(sessions)} sessions")
                
                # Cache results
                if context_cache and sessions:
                    context_cache.set(user_name, cache_key, sessions)
            
            # Inject context if we have sessions
            if sessions:
                logger.info(f"💉 Injecting {len(sessions)} sessions into context")
                success = inject_past_context(
                    context,
                    sessions,
                    user_name,
                    query_text=intent.query_text
                )
                if success:
                    logger.info("✅ Successfully injected past context")
                    return True
                else:
                    logger.warning("⚠️  Failed to inject past context")
            else:
                logger.info("ℹ️  No relevant sessions found for query")
            
            return False
            
        except Exception as e:
            logger.error(f"Error handling past reference query: {e}", exc_info=True)
            return False

    async def save_session_if_needed():
        """Save session summary if conditions are met."""
        try:
            logger.info(f"Attempting to save session summary for {user_name} (room: {room_name})")
            
            # Check if Supabase is enabled
            if not settings.SUPABASE_ENABLED:
                logger.info("Supabase is disabled, skipping session save")
                return
            
            duration = transcript_storage.get_duration_seconds()
            logger.info(f"Session duration: {duration:.1f} seconds")
            
            # Get message count from context first (more reliable)
            message_count = 0
            transcript = []
            try:
                messages = context.get_messages()
                if messages:
                    for msg in messages:
                        role = msg.get("role", "")
                        content = msg.get("content", "")
                        if role in ["user", "assistant"] and content and content.strip():
                            transcript.append({
                                "role": role,
                                "content": content.strip()
                            })
                    message_count = len(transcript)
                    logger.info(f"Found {message_count} messages in context")
                else:
                    logger.warning("No messages found in context")
                    # Fallback to transcript storage
                    message_count = transcript_storage.get_message_count()
                    transcript = transcript_storage.get_transcript()
                    logger.info(f"Using transcript storage: {message_count} messages")
            except Exception as e:
                logger.warning(f"Error getting messages from context: {e}", exc_info=True)
                message_count = transcript_storage.get_message_count()
                transcript = transcript_storage.get_transcript()

            # Minimum requirements: 30 seconds and 2 messages
            if duration < 30:
                logger.info(f"Session too short to save: {duration:.1f}s (minimum 30s required)")
                return
                
            if message_count < 2:
                logger.info(f"Not enough messages to save: {message_count} (minimum 2 required)")
                return

            # Check if session already exists
            if await check_session_exists(room_name):
                logger.info(f"Session {room_name} already saved, skipping")
                return

            # Validate transcript
            if not transcript or len(transcript) < 2:
                logger.warning(
                    f"Insufficient transcript for summary: {len(transcript)} messages. "
                    f"Minimum 2 required."
                )
                return

            logger.info(f"Generating summary for {len(transcript)} messages, duration: {duration:.1f}s")
            
            # Generate summary
            summary = await generate_session_summary(transcript, user_name, duration)
            
            if not summary or len(summary.strip()) < 10:
                logger.error("Generated summary is too short or empty, not saving")
                return
            
            logger.info(f"Generated summary ({len(summary)} chars): {summary[:100]}...")

            # Save to database
            success = await save_session_summary(
                user_name=user_name,
                room_name=room_name,
                summary=summary,
                duration_seconds=duration,
                message_count=message_count,
            )
            
            if success:
                logger.info(f"✅ Successfully saved session summary for {user_name} (room: {room_name})")
                # Invalidate cache for this user since new session was saved
                if context_cache:
                    context_cache.invalidate_user(user_name)
                    logger.debug(f"Invalidated cache for {user_name}")
            else:
                logger.error(f"❌ Failed to save session summary for {user_name} (room: {room_name})")

        except Exception as e:
            logger.error(f"Error saving session summary: {e}", exc_info=True)

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        """Handle participant joined event."""
        logger.info(f"👤 Participant joined: {participant.identity}")
        logger.info(f"   Session started at: {transcript_storage.session_start}")
        
        # Monitor messages for past references
        # Note: This is a simplified approach. In a production system, you might want
        # to hook into the message processing pipeline more directly.
        async def monitor_messages():
            """Monitor context messages for past references."""
            if not settings.ENABLE_DYNAMIC_CONTEXT:
                return
            
            try:
                messages = context.get_messages()
                if messages:
                    # Get the last user message
                    for msg in reversed(messages):
                        if msg.get("role") == "user":
                            user_message = msg.get("content", "")
                            if user_message:
                                await handle_past_reference_query(user_message)
                            break
            except Exception as e:
                logger.debug(f"Error monitoring messages: {e}")
        
        # Trigger the bot to greet the user immediately
        try:
            await task.queue_frames(
                [LLMMessagesFrame([{"role": "system", "content": "Say hello to the user briefly."}])]
            )
            logger.info("✅ Bot greeting queued")
        except Exception as e:
            logger.error(f"❌ Error greeting user: {e}", exc_info=True)

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, *args):
        """Handle participant left event."""
        logger.info("=" * 60)
        logger.info("👋 User left the room - attempting to save session summary")
        logger.info(f"   User: {user_name}")
        logger.info(f"   Room: {room_name}")
        # Save session summary before cleanup
        await save_session_if_needed()
        logger.info("Cleaning up task...")
        try:
            await task.cancel()
            logger.info("✅ Task canceled successfully")
        except Exception as e:
            logger.error(f"❌ Error canceling task: {e}", exc_info=True)
        logger.info("=" * 60)

    @transport.event_handler("on_call_ended")
    async def on_call_ended(transport):
        """Handle call ended event."""
        logger.info("=" * 60)
        logger.info("📞 Call ended by server - attempting to save session summary")
        logger.info(f"   User: {user_name}")
        logger.info(f"   Room: {room_name}")
        # Save session summary before cleanup
        await save_session_if_needed()
        logger.info("Cleaning up task...")
        try:
            await task.cancel()
            logger.info("✅ Task canceled successfully")
        except Exception as e:
            logger.error(f"❌ Error canceling task: {e}", exc_info=True)
        logger.info("=" * 60)

