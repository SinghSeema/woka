"""Bot entrypoint for LiveKit agent."""

import json
import os
import sys
from pathlib import Path
import asyncio
from datetime import datetime

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from livekit import api
from livekit.agents import JobContext, JobProcess, WorkerOptions, cli

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.observability import init_tracing, init_langfuse
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.transports.livekit.transport import LiveKitTransport, LiveKitParams

from bot.handlers.events import setup_event_handlers
from bot.services.llm_service import create_llm_service
from bot.services.stt_service import create_stt_service
from bot.services.tts_service import create_tts_service
from bot.services.transcript_storage import TranscriptStorage
from bot.services.context_cache import ContextCache
from bot.services.conversation_memory import ConversationMemory
from bot.services.shadow_memory import ShadowMemory
from bot.services.performance_monitor import get_performance_monitor
from bot.services.embedding_service import set_embedding_cache
from bot.services.langfuse_metrics import LangfuseMetrics, LlmRequestStartProcessor


# Setup logging
setup_logging()
logger = get_logger(__name__)


def prewarm(proc: JobProcess):
    """Pre-warm bot processes with heavy models."""
    try:
        logger.info("Pre-warming bot process (VAD)...")
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        proc.userdata["vad"] = SileroVADAnalyzer()
        logger.info("Bot engine warmed up.")
    except Exception as e:
        logger.error(f"Pre-warm failed: {e}")


async def entrypoint(ctx: JobContext):
    """Bot entrypoint for handling a job."""

    # Initialize observability inside entrypoint to avoid process startup timeouts
    try:
        if getattr(settings, "ENABLE_TRACING", False):
            init_tracing(service_name=settings.BOT_NAME)
        if getattr(settings, "ENABLE_LANGFUSE", False):
            init_langfuse()
    except Exception as _obs_err:
        logger.error(f"Observability initialization failed: {_obs_err}")

    pipeline_start_time = datetime.now()
    try:
        # Use the pre-warmed VAD from userdata
        vad_analyzer = ctx.proc.userdata.get("vad")
        if not vad_analyzer:
            logger.warning("VAD not pre-warmed, creating new instance")
            vad_analyzer = SileroVADAnalyzer()

        # Connect the worker to the room
        await ctx.connect(auto_subscribe=True)
        logger.info(f"Bot joined room: {ctx.room.name}")

        # OPTIMIZATION: Trigger non-blocking model pre-warm after joining
        if settings.ENABLE_SEMANTIC_SEARCH:
            from bot.services.embedding_service import generate_embedding
            # This triggers the model load in a background thread so it doesn't stall the pipeline
            asyncio.create_task(generate_embedding("warmup", use_cache=False))
            logger.info("🔥 Background embedding warm-up started")

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
            set_embedding_cache(context_cache)
            logger.info(f"✅ Initialized context cache (TTL: {settings.CONTEXT_CACHE_TTL}s)")
        
        # Initialize Shadow Memory for async pre-warming
        shadow_memory = None
        if settings.ENABLE_DYNAMIC_CONTEXT and context_cache:
            shadow_memory = ShadowMemory(context_cache, user_name)
            logger.info("✅ Initialized Shadow Memory")
        
        # Initialize conversation memory manager
        memory_manager = None
        if getattr(settings, 'ENABLE_CONVERSATION_MEMORY', True):
            memory_manager = ConversationMemory()
            logger.info("✅ Initialized conversation memory manager")
        
        # Initialize performance monitor
        performance_monitor = None
        if getattr(settings, 'ENABLE_PERFORMANCE_MONITORING', True):
            performance_monitor = get_performance_monitor()
            performance_monitor.start_session(user_name, ctx.room.name)
            logger.info("✅ Initialized performance monitor")

        # OPTIMIZATION: Skip past context loading at startup for faster pipeline initialization
        # Past context will be loaded on-demand via dynamic context queries if needed
        past_sessions_task = None
        if settings.SUPABASE_ENABLED:
            logger.debug("📚 Supabase enabled - past context will be loaded on-demand if needed")
        else:
            logger.debug("⚠️  Supabase disabled - no past sessions will be loaded")

        # Generate bot token
        token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(settings.BOT_NAME)
            .with_name(settings.BOT_NAME)
            .with_grants(api.VideoGrants(room_join=True, room=ctx.room.name))
        )
        logger.info(f"Bot token generated with identity: {settings.BOT_NAME}")

        # Create LiveKit transport
        logger.info(f"Creating LiveKit transport for room: {ctx.room.name}")
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
        logger.info(f"✅ LiveKit transport created")

        # OPTIMIZATION: Initialize services in parallel
        services_start_time = datetime.now()
        logger.info("Initializing services in parallel...")
        try:
            # Create services concurrently
            stt, llm, tts = await asyncio.gather(
                asyncio.to_thread(create_stt_service),
                asyncio.to_thread(create_llm_service),
                asyncio.to_thread(create_tts_service),
                return_exceptions=True
            )
            
            # Check for errors
            if isinstance(stt, Exception):
                logger.error(f"❌ Error creating STT service: {stt}", exc_info=True)
                raise stt
            if isinstance(llm, Exception):
                logger.error(f"❌ Error creating LLM service: {llm}", exc_info=True)
                raise llm
            if isinstance(tts, Exception):
                logger.error(f"❌ Error creating TTS service: {tts}", exc_info=True)
                raise tts
            
            services_duration = (datetime.now() - services_start_time).total_seconds()
            logger.info(f"✅ All services created successfully ({services_duration:.2f}s)")
        except Exception as e:
            logger.error(f"❌ Error creating services: {e}", exc_info=True)
            raise

        # OPTIMIZATION: Build system prompt WITHOUT past context for fast startup
        # Past context will be loaded on-demand via dynamic context queries if needed
        logger.debug("📋 Building system prompt (past context skipped for fast startup)...")
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

        ## INITIAL TASK
        Greet {user_name} and ask how their energy levels are today.
        """
        
        # Start with base prompt only (no past context)
        system_prompt = base_system_prompt_template
        messages = [{"role": "system", "content": system_prompt}]
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        
        logger.info(f"✅ Initial system prompt created ({len(system_prompt)} characters)")

        # Detect if this is an eval run (by room_name pattern or setting)
        is_eval = ctx.room.name.startswith("eval_") or getattr(settings, "ENVIRONMENT", "prod") == "eval"
        eval_run_id = None
        if is_eval:
            eval_run_id = ctx.room.name.split("_", 1)[1] if "_" in ctx.room.name else ctx.room.name
        
        # Always create observability processors for console logging and internal metrics
        # They will only send to Langfuse/OTel if enabled in settings
        from bot.services.langfuse_metrics import LlmRequestStartProcessor, LangfuseMetrics
        from bot.services.past_context_processor import PastContextProcessor

        langfuse_shared_state = {}
        llm_request_tracker = LlmRequestStartProcessor(shared_state=langfuse_shared_state)
        
        # Past context processor to handle dynamic history fetching BEFORE the LLM
        # This prevents the race condition where LLM responds before context is injected
        past_context_handler = PastContextProcessor(
            user_name=user_name,
            room_name=ctx.room.name,
            context=context,
            context_cache=context_cache
        )

        langfuse_metrics = LangfuseMetrics(
            user_name=user_name,
            room_name=ctx.room.name,
            environment="eval" if is_eval else "prod",
            eval_run_id=eval_run_id,
            shared_state=langfuse_shared_state,
        )
        logger.info(f"✅ Observability processors created (env={'eval' if is_eval else 'prod'})")
        
        # Build pipeline with observability
        logger.info("Building pipeline...")
        pipeline_components = [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm_request_tracker,
            past_context_handler,
            llm,
            langfuse_metrics,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
        
        pipeline = Pipeline(pipeline_components)

        task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

        # Setup event handlers
        handlers_start_time = datetime.now()
        logger.info("Setting up event handlers...")
        await setup_event_handlers(
            transport, task, transcript_storage, user_name, ctx.room.name, context, 
            context_cache, memory_manager, performance_monitor, shadow_memory
        )
        handlers_duration = (datetime.now() - handlers_start_time).total_seconds()
        logger.info(f"✅ Event handlers configured ({handlers_duration:.2f}s)")

        # OPTIMIZATION: Pre-warm Shadow Memory asynchronously (non-blocking)
        # This fetches last 3-5 sessions in background and injects them into system prompt
        if shadow_memory and settings.SUPABASE_ENABLED:
            if settings.MAX_PAST_SESSIONS <= 0:
                logger.info("⏭️  Shadow Memory pre-warming disabled (MAX_PAST_SESSIONS=0)")
            else:
                logger.info("🔥 Pre-warming Shadow Memory in background...")
                # Run pre-warming as background task (don't await, non-blocking)
                # Pass context so pre-warmed sessions can be injected into system prompt
                asyncio.create_task(
                    shadow_memory.prewarm(
                        limit=settings.MAX_PAST_SESSIONS, inject_into_context=context
                    )
                )
                logger.info("✅ Shadow Memory pre-warming started (non-blocking, will inject into prompt when ready)")

        # OPTIMIZATION: Past context loading is skipped at startup for faster initialization
        # Past context will be loaded on-demand via dynamic context queries when user asks about past sessions
        # Shadow Memory pre-warms common queries in background for instant cache hits
        # This allows the pipeline to start immediately with basic system prompt only

        # Calculate pipeline initialization time
        pipeline_init_duration = (datetime.now() - pipeline_start_time).total_seconds()
        logger.info(f"⏱️  Pipeline initialization completed in {pipeline_init_duration:.2f}s")

        # Run pipeline (this is non-blocking for the background task)
        logger.info("🚀 Starting pipeline runner - session is now active")
        logger.info(f"   User: {user_name} | Room: {ctx.room.name}")
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

