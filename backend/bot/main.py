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
from bot.services.transcript_storage import TranscriptStorage
from bot.services.database_service import get_past_sessions
from bot.services.context_manager import (
    build_past_context,
    validate_context_size,
    estimate_tokens
)
from bot.services.context_cache import ContextCache

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
        logger.info(f"Room name: {ctx.room.name}")

        # Initialize transcript storage
        transcript_storage = TranscriptStorage()
        transcript_storage.set_session_id(ctx.room.name)
        logger.info(f"Initialized transcript storage for session: {ctx.room.name}")

        # Initialize context cache for dynamic queries
        context_cache = None
        if settings.ENABLE_DYNAMIC_CONTEXT:
            context_cache = ContextCache(ttl_seconds=settings.CONTEXT_CACHE_TTL)
            logger.info(f"✅ Initialized context cache (TTL: {settings.CONTEXT_CACHE_TTL}s)")
        
        # Fetch past sessions for agentic memory
        past_sessions = []
        if settings.SUPABASE_ENABLED:
            logger.info("=" * 60)
            logger.info(f"📚 Fetching past session summaries for agentic memory")
            logger.info(f"   User: {user_name}")
            initial_count = settings.INITIAL_SESSIONS_COUNT if settings.ENABLE_DYNAMIC_CONTEXT else settings.MAX_PAST_SESSIONS
            logger.info(f"   Limit: {initial_count} most recent sessions")
            try:
                past_sessions = await get_past_sessions(user_name, limit=initial_count)
                logger.info(f"✅ Retrieved {len(past_sessions)} past sessions for {user_name}")
                if past_sessions:
                    logger.info(f"   Most recent session: {past_sessions[0].get('created_at', 'unknown')}")
                    # Log summary of each session being loaded
                    logger.info("   Loading session summaries into bot context:")
                    for i, session in enumerate(past_sessions[:5], 1):  # Log first 5
                        summary = session.get("summary", "")
                        created_at = session.get("created_at", "")
                        date_str = created_at[:10] if created_at and len(created_at) >= 10 else "unknown"
                        summary_preview = summary[:80] + "..." if len(summary) > 80 else summary
                        logger.info(f"      Session {i} ({date_str}): {summary_preview}")
                    if len(past_sessions) > 5:
                        logger.info(f"      ... and {len(past_sessions) - 5} more sessions")
                else:
                    logger.info("   No past sessions found - this is a new user")
            except Exception as e:
                logger.warning(f"❌ Error fetching past sessions: {e}", exc_info=True)
            logger.info("=" * 60)
        else:
            logger.info("⚠️  Supabase disabled - no past sessions will be loaded")

        # Generate bot token
        # Use BOT_NAME as identity so frontend can find the bot participant
        token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(settings.BOT_NAME)
            .with_name(settings.BOT_NAME)
            .with_grants(api.VideoGrants(room_join=True, room=ctx.room.name))
        )
        logger.info(f"Bot token generated with identity: {settings.BOT_NAME}, name: {settings.BOT_NAME}")

        # Create LiveKit transport
        logger.info(f"Creating LiveKit transport for room: {ctx.room.name}")
        logger.info(f"Bot identity: bot-{ctx.job.id}, Bot name: {settings.BOT_NAME}")
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
        logger.info(f"✅ LiveKit transport created with audio_out_enabled=True")

        # Setup services
        logger.info("Initializing services...")
        try:
            stt = create_stt_service()
            logger.info("✅ STT service created")
        except Exception as e:
            logger.error(f"❌ Error creating STT service: {e}", exc_info=True)
            raise
        
        try:
            llm = create_llm_service()
            logger.info("✅ LLM service created")
        except Exception as e:
            logger.error(f"❌ Error creating LLM service: {e}", exc_info=True)
            raise
        
        try:
            tts = create_tts_service()
            logger.info("✅ TTS service created")
        except Exception as e:
            logger.error(f"❌ Error creating TTS service: {e}", exc_info=True)
            raise

        # Build system prompt with past session context (agentic memory)
        # Use context manager to build and validate past context
        past_context, sessions_included = build_past_context(past_sessions, user_name)
        if past_context:
            logger.info(f"✅ Past session context prepared ({len(past_context)} characters)")
            logger.info(f"   Includes {sessions_included} session summaries with dates, durations, and summaries")
        else:
            logger.info("ℹ️  No past sessions available - bot will start fresh")

        # Initialize context with user's name
        logger.info("📋 Building system prompt for bot...")
        # Build base system prompt template (without past_context)
        base_system_prompt_template = f"""
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
        {{past_context_placeholder}}

        ## INITIAL TASK
        Greet {user_name} and ask how their energy levels are today.
        """
        # Calculate base prompt (without past_context) for validation
        base_system_prompt = base_system_prompt_template.replace("{past_context_placeholder}", "")
        base_prompt_size = len(base_system_prompt)
        # Build full system prompt with past_context
        system_prompt = base_system_prompt_template.replace("{past_context_placeholder}", past_context)

        messages = [{"role": "system", "content": system_prompt}]
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        
        # Validate and log context sizes
        prompt_length = len(system_prompt)
        has_past_context = len(past_context) > 0
        
        # Validate context size (model context window: 128K for llama-3.3-70b-versatile)
        # Pass base prompt separately so validation checks base against its threshold, not total
        is_valid, warning = validate_context_size(
            system_prompt,
            past_context,
            model_context_window=128000,  # llama-3.3-70b-versatile context window
            base_system_prompt=base_system_prompt
        )
        
        if not is_valid:
            logger.error(f"❌ Context validation failed: {warning}")
            raise ValueError(f"Context size validation failed: {warning}")
        
        if warning:
            logger.warning(f"⚠️  Context validation warning: {warning}")
        
        # Log system prompt summary
        system_tokens = estimate_tokens(system_prompt)
        past_tokens = estimate_tokens(past_context) if past_context else 0
        total_tokens = system_tokens + past_tokens
        
        logger.info(f"✅ System prompt created ({prompt_length} characters, ~{system_tokens} tokens)")
        logger.info(f"   Includes past session context: {'Yes' if has_past_context else 'No'}")
        if has_past_context:
            logger.info(f"   Past context size: {len(past_context)} characters (~{past_tokens} tokens)")
            logger.info(f"   Bot is ready with agentic memory from {sessions_included} past sessions")
        logger.info(f"   Total context: ~{total_tokens} tokens (system + past context, excluding conversation history)")

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

        # Setup event handlers with transcript storage and context cache
        logger.info("Setting up event handlers (including session save on disconnect)...")
        await setup_event_handlers(
            transport, task, transcript_storage, user_name, ctx.room.name, context, context_cache
        )
        logger.info("✅ Event handlers configured - session will be saved on disconnect")
        if context_cache:
            logger.info(f"   Dynamic context querying enabled (cache TTL: {settings.CONTEXT_CACHE_TTL}s)")

        # Run pipeline
        logger.info("🚀 Starting pipeline runner - session is now active")
        logger.info(f"   User: {user_name}")
        logger.info(f"   Room: {ctx.room.name}")
        logger.info(f"   Bot name: {settings.BOT_NAME}")
        logger.info(f"   Bot identity: bot-{ctx.job.id}")
        logger.info(f"   Supabase enabled: {settings.SUPABASE_ENABLED}")
        logger.info(f"   Audio out enabled: True")
        logger.info(f"   Audio in enabled: True")
        try:
            runner = PipelineRunner()
            await runner.run(task)
            logger.info("⏹️  Pipeline runner stopped")
        except Exception as e:
            logger.error(f"❌ Error in pipeline runner: {e}", exc_info=True)
            raise

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

