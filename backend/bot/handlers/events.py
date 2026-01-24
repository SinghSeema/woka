"""Bot event handlers."""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.summary_service import generate_session_summary
from bot.services.database_service import save_session_summary, check_session_exists

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
) -> None:
    """Setup event handlers for transport.

    Args:
        transport: LiveKit transport instance.
        task: Pipeline task instance.
        transcript_storage: Transcript storage instance.
        user_name: User's display name.
        room_name: Room name.
        context: LLM context for accessing messages.
    """
    from pipecat.frames.frames import LLMMessagesFrame

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
            else:
                logger.error(f"❌ Failed to save session summary for {user_name} (room: {room_name})")

        except Exception as e:
            logger.error(f"Error saving session summary: {e}", exc_info=True)

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        """Handle participant joined event."""
        logger.info(f"👤 Participant joined: {participant.identity}")
        logger.info(f"   Session started at: {transcript_storage.session_start}")
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

