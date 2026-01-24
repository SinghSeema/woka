"""Bot entrypoint for LiveKit agent."""

import json
import os
import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from livekit import api
from livekit.agents import JobContext, JobProcess, WorkerOptions, cli
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.transports.livekit.transport import LiveKitTransport, LiveKitParams

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from bot.handlers.events import setup_event_handlers
from bot.services.llm_service import create_llm_service
from bot.services.stt_service import create_stt_service
from bot.services.tts_service import create_tts_service

# Setup logging
setup_logging()
logger = get_logger(__name__)


def prewarm(proc: JobProcess):
    """Pre-warm bot processes with heavy models.

    Args:
        proc: Job process instance.
    """
    logger.info("Pre-warming bot process...")
    # Load the heavy local VAD model
    vad_analyzer = SileroVADAnalyzer()
    proc.userdata["vad"] = vad_analyzer
    logger.info("Bot engine warmed up.")


async def entrypoint(ctx: JobContext):
    """Bot entrypoint for handling a job.

    Args:
        ctx: Job context from LiveKit.
    """
    try:
        # Use the pre-warmed VAD from userdata
        vad_analyzer = ctx.proc.userdata.get("vad")
        if not vad_analyzer:
            logger.warning("VAD not pre-warmed, creating new instance")
            vad_analyzer = SileroVADAnalyzer()

        # Connect the worker to the room
        await ctx.connect(auto_subscribe=True)
        logger.info(f"Bot joined room: {ctx.room.name}")

        # Get user metadata (Name, etc.) passed from server
        user_name = "Guest"
        for participant in ctx.room.remote_participants.values():
            if participant.metadata:
                try:
                    meta = json.loads(participant.metadata)
                    user_name = meta.get("user_name", "Guest")
                    break
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse participant metadata: {participant.metadata}")

        logger.info(f"User name: {user_name}")

        # Generate bot token
        token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(f"bot-{ctx.job.id}")
            .with_name(settings.BOT_NAME)
            .with_grants(api.VideoGrants(room_join=True, room=ctx.room.name))
        )

        # Create LiveKit transport
        transport = LiveKitTransport(
            url=settings.LIVEKIT_URL,
            token=token.to_jwt(),
            room_name=ctx.room.name,
            params=LiveKitParams(
                audio_out_enabled=True,
                audio_in_enabled=True,
                vad_enabled=True,
                vad_analyzer=vad_analyzer,
                vad_threshold=settings.VAD_THRESHOLD,
            ),
        )

        # Setup services
        logger.info("Initializing services...")
        stt = create_stt_service()
        llm = create_llm_service()
        tts = create_tts_service()

        # Initialize context with user's name
        system_prompt = f"""
        ## ROLE
        You are "{settings.BOT_NAME}," an empathetic, professional, and motivational Wellness Coach. Your goal is to help {user_name} achieve their health goals through lifestyle, habit formation, and positive mindset shifts.

        ## CORE PRINCIPLES
        1. **Scope of Practice:** You provide advice on nutrition, exercise, sleep, and stress management. 
        2. **Safety First:** You are NOT a doctor, therapist, or medical professional. 
        3. **Guardrails:** If {user_name} asks for medical diagnoses, prescriptions, or advice on chronic illnesses/injuries, you must refuse and redirect to a professional.
        4. **Ethics:** Never encourage extreme diets, self-harm, or dangerous physical activities. If a request is "wrong" or potentially harmful, politely decline.

        ## BOUNDARIES & DISCLAIMERS
        - **Mandatory Disclaimer:** If a user asks about a health condition, start with: "I'm here to support your wellness journey, but I'm not a medical professional. Please consult a doctor for medical concerns."
        - **Refusal Protocol:** If the user asks something outside your scope or unethical, say: "I'm focused on wellness coaching (habits, movement, and mindset). I cannot provide advice on [Topic], as that falls outside my expertise."

        ## STYLE & TONE
        - **Tone:** Grounded, encouraging, and clear. 
        - **Style:** Keep responses concise (ideal for voice interaction). Avoid long lists.
        - **Greeting:** Start by warmly greeting {user_name} and acknowledging their progress.

        ## INITIAL TASK
        Greet {user_name} and ask how their energy levels are today.
        """

        messages = [{"role": "system", "content": system_prompt}]
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)

        # Build pipeline
        logger.info("Building pipeline...")
        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                context_aggregator.user(),
                llm,
                tts,
                transport.output(),
                context_aggregator.assistant(),
            ]
        )

        task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

        # Setup event handlers
        await setup_event_handlers(transport, task)

        # Run pipeline
        logger.info("Starting pipeline runner...")
        runner = PipelineRunner()
        await runner.run(task)

    except Exception as e:
        logger.error(f"Error in bot entrypoint: {e}", exc_info=True)
        raise


def compute_load(worker):
    """Compute worker load.

    Args:
        worker: Worker instance.

    Returns:
        Load value between 0 and 1.
    """
    return min(len(worker.active_jobs) / 5, 1.0)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            num_idle_processes=settings.NUM_IDLE_PROCESSES,
        )
    )

