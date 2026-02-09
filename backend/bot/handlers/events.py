"""Bot event handlers."""

import sys
import asyncio
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
    get_sessions_by_topic, get_all_sessions,
    save_chunk_question_rows
)
from bot.services.chunk_question_index import build_chunk_question_rows
from bot.services.intent_detector import detect_past_reference_intent
from bot.services.context_injector import inject_past_context
from bot.services.context_cache import ContextCache, generate_cache_key
from bot.services.conversation_memory import ConversationMemory, monitor_conversation_memory
from bot.services.memory_compressor import (
    summarize_conversation_segment,
    inject_summary_into_context,
    remove_old_messages
)
from bot.services.shadow_memory import ShadowMemory
from bot.services.filler_generator import generate_filler, should_use_filler
from bot.services.performance_monitor import get_performance_monitor
from bot.services.cost_tracker import estimate_session_cost, log_cost_summary
from datetime import datetime
import time
import random

from app.core.observability import (
    get_tracer,
    record_context_fetch_event,
    record_turn_metrics_event,
    record_session_event,
)

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
    memory_manager: ConversationMemory = None,
    performance_monitor = None,
    shadow_memory: ShadowMemory = None,
) -> None:
    """Setup event handlers for transport."""
    from pipecat.frames.frames import LLMMessagesFrame
    
# NOTE: Past reference dynamic context fetching is now handled exclusively
# by `PastContextProcessor` in the pipeline. The event handlers here focus on:
# - TTFT / full turn duration metrics
# - Conversation memory compression
# - Session summary generation and Supabase persistence

async def setup_event_handlers(
    transport,
    task: "PipelineTask",
    transcript_storage: "TranscriptStorage",
    user_name: str,
    room_name: str,
    context: "OpenAILLMContext",
    context_cache: ContextCache = None,
    memory_manager: ConversationMemory = None,
    performance_monitor = None,
    shadow_memory: ShadowMemory = None,
) -> None:
    """Setup event handlers for transport."""
    from pipecat.frames.frames import LLMMessagesFrame
    
    # Initialize memory manager if not provided
    
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
            
            # Generate summary and extract topics (pass performance monitor to track tokens)
            summary, topics = await generate_session_summary(
                transcript, user_name, duration,
                performance_monitor=performance_monitor,
                room_name=room_name
            )
            
            if not summary or len(summary.strip()) < 10:
                logger.error("Generated summary is too short or empty, not saving")
                return
            
            logger.info(f"Generated summary ({len(summary)} chars): {summary[:100]}...")
            if topics:
                logger.info(f"Extracted {len(topics)} topics: {topics}")
            else:
                logger.warning(f"No topics extracted from session (topics={topics})")

            # Save to database with topics
            success = await save_session_summary(
                user_name=user_name,
                room_name=room_name,
                summary=summary,
                topics=topics,
                duration_seconds=duration,
                message_count=message_count,
            )
            
            if success:
                logger.info(f"✅ Successfully saved session summary for {user_name} (room: {room_name})")
                # Invalidate cache for this user since new session was saved
                if context_cache:
                    context_cache.invalidate_user(user_name)
                    logger.debug(f"Invalidated cache for {user_name}")

                # Optional: index chunk questions for semantic recall
                if settings.ENABLE_CHUNK_QUESTION_INDEX:
                    try:
                        rows = await build_chunk_question_rows(transcript, user_name, room_name)
                        if rows:
                            inserted = await save_chunk_question_rows(rows)
                            logger.info(f"✅ Indexed {inserted} chunk-question rows for {room_name}")
                        else:
                            logger.debug("No chunk questions generated for indexing")
                    except Exception as e:
                        logger.error(f"Chunk question indexing failed: {e}", exc_info=True)
            else:
                logger.error(f"❌ Failed to save session summary for {user_name} (room: {room_name})")

        except Exception as e:
            logger.error(f"Error saving session summary: {e}", exc_info=True)

    monitoring_started = False

    async def _start_session_monitoring(participant_id: str):
        """Start session monitoring once when the first participant joins."""
        nonlocal monitoring_started
        if monitoring_started:
            return
        monitoring_started = True

        logger.info(f"👤 Participant joined: {participant_id}")
        logger.info(f"   Session started at: {transcript_storage.session_start}")

        # Record session start in Langfuse (if configured)
        record_session_event(
            event_name="session_started",
            user_name=user_name,
            room_name=room_name,
            properties={"participant_id": participant_id},
        )
        
        # Track last processed message to avoid reprocessing
        last_processed_message = {"content": "", "count": 0}
        user_message_timestamps = {}  # Track when user messages were received for TTFT
        last_turn_used_past_context = False  # Track if past context was used in current turn
        
        # Extract core processing logic (event-based, no polling)
        async def process_messages(messages):
            """Process messages for past references, TTFT, and memory management.
            
            This is called event-based when context changes, not via polling.
            """
            if not messages:
                return
            
            try:
                nonlocal last_turn_used_past_context
                # Get the last user message
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        user_message = msg.get("content", "")
                        if user_message and (
                            user_message != last_processed_message["content"]
                            or len(messages) != last_processed_message["count"]
                        ):
                            # New message detected - track timestamp for TTFT
                            user_message_timestamps[user_message] = datetime.now()
                            last_processed_message["content"] = user_message
                            last_processed_message["count"] = len(messages)
                            
                            # Reset context flag for new turn
                            last_turn_used_past_context = False
                            
                            # Note: Past reference query handling has been moved to 
                            # PastContextProcessor in the pipeline to prevent race conditions.
                            # The observer still monitors messages for TTFT and memory.
                        break
                
                # Check for TTFT: when assistant responds after user message
                for i, msg in enumerate(messages):
                    if msg.get("role") == "assistant" and i > 0:
                        # Find the most recent user message before this assistant message
                        user_msg = ""
                        for j in range(i - 1, -1, -1):
                            if messages[j].get("role") == "user":
                                user_msg = messages[j].get("content", "")
                                break

                        if user_msg and user_msg in user_message_timestamps:
                            turn_duration_ms = (datetime.now() - user_message_timestamps[user_msg]).total_seconds() * 1000
                            logger.info(f"⏱️  Full Turn Duration: {turn_duration_ms:.0f}ms")
                            
                            # Record in performance monitor
                            if performance_monitor:
                                performance_monitor.record_request(
                                    user_name, room_name, "full_turn_duration", turn_duration_ms, success=True
                                )
                            
                            # Send per-turn metrics to Langfuse (sampled/gated)
                            if getattr(settings, "LANGFUSE_TURN_METRICS_ENABLED", True):
                                if not (settings.is_production and not getattr(settings, "LANGFUSE_TURN_METRICS_IN_PROD", True)):
                                    sample_rate = float(getattr(settings, "LANGFUSE_TURN_SAMPLE_RATE", 1.0))
                                    if sample_rate >= 1.0 or (sample_rate > 0.0 and random.random() <= sample_rate):
                                        record_turn_metrics_event(
                                            user_name=user_name,
                                            room_name=room_name,
                                            ttft_ms=turn_duration_ms,
                                            used_past_context=last_turn_used_past_context,
                                        )
                            
                            # Remove from tracking
                            del user_message_timestamps[user_msg]
                
                # Check memory management
                await check_and_summarize_memory()
                
                # Update Shadow Memory after response (background, non-blocking)
                await update_shadow_memory_after_response()
            except Exception as e:
                logger.debug(f"Error processing messages: {e}")
        
        # Event-based context observer (replaces polling) - attach to the real context object
        def attach_message_observer():
            original_get_messages = context.get_messages
            # state includes a reentrancy guard to prevent loops
            state = {"last_count": 0, "processing": False, "in_wrapper": False}

            async def on_message_changed(messages):
                try:
                    await process_messages(messages)
                finally:
                    state["processing"] = False

            def get_messages_wrapper():
                # Re-entrancy guard: if we are already inside the wrapper, 
                # just return the messages without triggering a new task.
                if state["in_wrapper"]:
                    return original_get_messages()
                
                state["in_wrapper"] = True
                try:
                    msgs = original_get_messages()
                    current_count = len(msgs) if msgs else 0
                    
                    # Only trigger if the count actually changed AND we aren't already processing
                    if current_count != state["last_count"] and not state["processing"]:
                        state["last_count"] = current_count
                        # Set processing flag IMMEDIATELY before spawning task to prevent race conditions
                        state["processing"] = True
                        asyncio.create_task(on_message_changed(msgs))
                    return msgs
                finally:
                    state["in_wrapper"] = False

            context.get_messages = get_messages_wrapper
        
        async def check_and_summarize_memory():
            """Check if memory compression is needed and perform it.
            
            Implements Strategy 4: Semantic Context Compression with Running Summaries.
            """
            if not memory_manager or not getattr(settings, "ENABLE_CONVERSATION_MEMORY", True):
                return
            if not getattr(settings, "ENABLE_INCREMENTAL_SUMMARIES", True):
                return
            
            try:
                # 1. Proactive Safety: Prune context if it exceeds hard limits (Context Guard)
                # This prevents TPD limit overflows even if summarization hasn't happened yet
                from bot.services.context_manager import prune_context_if_needed
                messages = context.get_messages()
                
                # Max tokens for history is set to 4000 (~16k chars) to stay within safe TPD
                pruned_messages, was_pruned = prune_context_if_needed(
                    messages, 
                    max_tokens=4000, 
                    keep_recent=10
                )
                if was_pruned:
                    context.get_messages()[:] = pruned_messages
                    logger.info("🛡️ Context Guard: Pruned middle messages to protect TPD limits")
                
                # 2. Strategic Summarization: Periodic compression into running summary
                status = monitor_conversation_memory(context, memory_manager)
                
                if not status.get("should_summarize", False):
                    return
                
                logger.info(
                    f"📊 Memory compression triggered: {status.get('message_count', 0)} messages, "
                    f"{status.get('estimated_tokens', 0)} tokens"
                )
                
                # Get messages to compress
                to_summarize, to_keep = memory_manager.get_messages_to_summarize(messages)
                
                if not to_summarize:
                    return
                
                # Summarize segment and merge into running summary
                new_summary = await summarize_conversation_segment(
                    to_summarize, 
                    user_name,
                    previous_summary=memory_manager.running_summary
                )
                
                if new_summary:
                    # Update memory manager state
                    memory_manager.running_summary = new_summary
                    
                    # Calculate message range
                    message_range = (
                        len(messages) - len(to_summarize) - len(to_keep),
                        len(messages) - len(to_keep)
                    )
                    
                    # Inject into context (handles replacement if already exists)
                    success = inject_summary_into_context(context, new_summary, message_range)
                    
                    if success:
                        # Remove full-text messages that were summarized
                        removed_count = remove_old_messages(context, to_summarize)
                        memory_manager.record_summarization(len(messages) - removed_count)
                        memory_manager.add_rolling_summary(new_summary, message_range)
                        
                        logger.info(
                            f"✅ Session continuity preserved via updated running summary "
                            f"({len(new_summary)} chars)"
                        )
                    else:
                        logger.warning("Failed to inject summary into context")
                else:
                    logger.warning("Failed to generate summary for memory compression")
                    
            except Exception as e:
                logger.error(f"Error in memory compression: {e}", exc_info=True)
        
        async def update_shadow_memory_after_response():
            """Update Shadow Memory cache after LLM response (background, non-blocking)."""
            if shadow_memory:
                try:
                    # Update cache in background (don't block)
                    await shadow_memory.update_after_response()
                except Exception as e:
                    logger.debug(f"Error updating Shadow Memory (non-critical): {e}")
        
        # Always attach observer so TTFT is tracked even when dynamic context is off
        attach_message_observer()
        logger.debug("✅ Event-based message monitoring enabled (triggers on context change)")
        
        # Trigger the bot to greet the user immediately
        try:
            await task.queue_frames(
                [LLMMessagesFrame([{"role": "system", "content": "Say hello to the user briefly."}])]
            )
            logger.info("✅ Bot greeting queued")
        except Exception as e:
            logger.error(f"❌ Error greeting user: {e}", exc_info=True)

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant_id: str):
        """Handle first participant joined event (LiveKit)."""
        await _start_session_monitoring(participant_id)

    @transport.event_handler("on_participant_connected")
    async def on_participant_connected(transport, participant_id: str):
        """Handle participant connected event (LiveKit)."""
        await _start_session_monitoring(participant_id)

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, *args):
        """Handle participant left event."""
        logger.info("=" * 60)
        logger.info("👋 User left the room - attempting to save session summary")
        logger.info(f"   User: {user_name}")
        logger.info(f"   Room: {room_name}")
        
        # Log performance and cost summary
        if performance_monitor:
            metrics = performance_monitor.get_session_metrics(user_name, room_name)
            if metrics and getattr(settings, 'TRACK_COSTS', True):
                cost_breakdown = estimate_session_cost(
                    total_input_tokens=metrics.get('total_tokens_input', 0),
                    total_output_tokens=metrics.get('total_tokens_output', 0),
                    embedding_tokens=0  # Could track this separately if needed
                )
                log_cost_summary(user_name, room_name, cost_breakdown)
        
        # Save session summary before cleanup
        await save_session_if_needed()
        
        # Cleanup performance monitoring
        if performance_monitor:
            performance_monitor.cleanup_session(user_name, room_name)
        
        logger.info("Cleaning up task...")
        try:
            await task.cancel()
            logger.info("✅ Task canceled successfully")
        except Exception as e:
            logger.error(f"❌ Error canceling task: {e}", exc_info=True)
        logger.info("=" * 60)

    @transport.event_handler("on_call_state_updated")
    async def on_call_state_updated(transport, state: str):
        """Handle call state updates (LiveKit)."""
        if state not in {"ended", "disconnected", "terminated"}:
            return

        logger.info("=" * 60)
        logger.info(f"📞 Call state updated: {state} - attempting to save session summary")
        logger.info(f"   User: {user_name}")
        logger.info(f"   Room: {room_name}")

        # Record session end in Langfuse (if configured)
        record_session_event(
            event_name="session_ended",
            user_name=user_name,
            room_name=room_name,
            properties={"state": state},
        )
        
        # Log performance and cost summary
        if performance_monitor:
            metrics = performance_monitor.get_session_metrics(user_name, room_name)
            if metrics and getattr(settings, 'TRACK_COSTS', True):
                cost_breakdown = estimate_session_cost(
                    total_input_tokens=metrics.get('total_tokens_input', 0),
                    total_output_tokens=metrics.get('total_tokens_output', 0),
                    embedding_tokens=0  # Could track this separately if needed
                )
                log_cost_summary(user_name, room_name, cost_breakdown)
        
        # Save session summary before cleanup
        await save_session_if_needed()
        
        # Cleanup performance monitoring
        if performance_monitor:
            performance_monitor.cleanup_session(user_name, room_name)
        
        logger.info("Cleaning up task...")
        try:
            await task.cancel()
            logger.info("✅ Task canceled successfully")
        except Exception as e:
            logger.error(f"❌ Error canceling task: {e}", exc_info=True)
        logger.info("=" * 60)

