"""Bot event handlers."""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.logging import get_logger

if TYPE_CHECKING:
    from pipecat.pipeline.task import PipelineTask

logger = get_logger(__name__)


async def setup_event_handlers(transport, task: "PipelineTask") -> None:
    """Setup event handlers for transport.

    Args:
        transport: LiveKit transport instance.
        task: Pipeline task instance.
    """
    from pipecat.frames.frames import LLMMessagesFrame

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        """Handle participant joined event."""
        logger.info(f"Participant joined: {participant.identity}")
        # Trigger the bot to greet the user immediately
        try:
            await task.queue_frames(
                [LLMMessagesFrame([{"role": "system", "content": "Say hello to the user briefly."}])]
            )
        except Exception as e:
            logger.error(f"Error greeting user: {e}", exc_info=True)

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, *args):
        """Handle participant left event."""
        logger.info("User left the room. Cleaning up...")
        # Trigger the summary and transcript before we kill the task
        # await generate_session_summary(context)
        # await save_transcript(room_name, context.get_messages())
        try:
            await task.cancel()
        except Exception as e:
            logger.error(f"Error canceling task: {e}", exc_info=True)

    @transport.event_handler("on_call_ended")
    async def on_call_ended(transport):
        """Handle call ended event."""
        logger.info("Call ended by server. Exiting...")
        try:
            await task.cancel()
        except Exception as e:
            logger.error(f"Error canceling task: {e}", exc_info=True)

