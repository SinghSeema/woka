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

        # Fetch past sessions for agentic memory
        past_sessions = []
        if settings.SUPABASE_ENABLED:
            logger.info("=" * 60)
            logger.info(f"📚 Fetching past session summaries for agentic memory")
            logger.info(f"   User: {user_name}")
            logger.info(f"   Limit: 10 most recent sessions")
            try:
                past_sessions = await get_past_sessions(user_name, limit=10)
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

        # Build system prompt with past session context (agentic memory)
        past_context = ""
        if past_sessions:
            logger.info(f"📝 Building system prompt with {len(past_sessions)} past session summaries")
            past_context = "\n\n## PAST SESSIONS CONTEXT (Agentic Memory)\n"
            past_context += f"You have access to summaries from {len(past_sessions)} recent sessions with {user_name}. "
            past_context += "This enables you to provide continuity, remember their journey, and answer questions about past conversations.\n\n"
            past_context += "**Your capabilities with past sessions:**\n"
            past_context += "1. **Remember & Reference**: You can remember goals, concerns, progress, and topics from past sessions\n"
            past_context += "2. **Answer Questions**: When {user_name} asks about past sessions (e.g., 'What did we discuss last time?', 'What was my goal?'), you can reference the summaries below\n"
            past_context += "3. **Provide Continuity**: Reference past conversations naturally when relevant to current topics\n"
            past_context += "4. **Track Progress**: Acknowledge achievements, changes, or progress mentioned across sessions\n"
            past_context += "5. **Share Context**: When asked, you can share specific information from past sessions (e.g., 'In our session on [date], we discussed...')\n\n"
            past_context += "**Recent session summaries (most recent first):**\n\n"
            
            for i, session in enumerate(past_sessions[:10], 1):
                summary = session.get("summary", "")
                created_at = session.get("created_at", "")
                duration = session.get("duration_seconds", 0)
                message_count = session.get("message_count", 0)
                
                # Format date nicely
                date_str = "recent"
                date_display = "recently"
                if created_at:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        date_str = dt.strftime("%Y-%m-%d")
                        # Create a more readable date format
                        date_display = dt.strftime("%B %d, %Y")  # e.g., "January 15, 2024"
                    except:
                        date_str = created_at[:10] if len(created_at) >= 10 else "recent"
                        date_display = date_str
                
                # Format duration
                duration_min = int(duration / 60) if duration else 0
                
                past_context += f"**Session {i}** - {date_display} ({date_str})\n"
                past_context += f"Duration: {duration_min} minutes | Messages: {message_count}\n"
                past_context += f"Summary: {summary}\n\n"
            
            past_context += "**Guidelines for using past context:**\n"
            past_context += f"- **When {user_name} asks about past sessions**: Reference the specific session(s) and share relevant information\n"
            past_context += "- **When topics connect**: Naturally reference past conversations (e.g., 'Last time we discussed your sleep schedule...')\n"
            past_context += "- **When acknowledging progress**: Reference past sessions to show continuity (e.g., 'I remember you mentioned...')\n"
            past_context += "- **Be specific**: When sharing from past sessions, mention the date or session number if helpful\n"
            past_context += "- **Don't force it**: Only reference past sessions when it adds value or when the user asks\n"
            past_context += "- **Be warm and personal**: Show you remember their journey and care about their progress\n"
            past_context += "- **Multiple sessions**: You can reference and combine information from multiple past sessions when relevant. For example, if asked about progress over time, reference multiple sessions to show the journey\n"
            past_context += f"- **User questions**: If {user_name} asks 'What did we talk about before?', 'What was my goal?', 'What progress have I made?', or 'What did we discuss about [topic]?', use the summaries above to provide specific, detailed answers\n"
            past_context += "- **Cross-session patterns**: When you notice patterns or themes across multiple sessions, you can reference them (e.g., 'I've noticed across our sessions that you've been working on...')\n"
            past_context += "- **Timeline awareness**: You can reference the timeline of sessions (e.g., 'In our earlier sessions, you mentioned... and more recently, you've been focusing on...')"
            
            logger.info(f"✅ Past session context prepared ({len(past_context)} characters)")
            logger.info(f"   Includes {len(past_sessions)} session summaries with dates, durations, and full summaries")
        else:
            logger.info("ℹ️  No past sessions available - bot will start fresh")

        # Initialize context with user's name
        logger.info("📋 Building system prompt for bot...")
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
        {past_context}

        ## INITIAL TASK
        Greet {user_name} and ask how their energy levels are today.
        """

        messages = [{"role": "system", "content": system_prompt}]
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        
        # Log system prompt summary
        prompt_length = len(system_prompt)
        has_past_context = len(past_context) > 0
        logger.info(f"✅ System prompt created ({prompt_length} characters)")
        logger.info(f"   Includes past session context: {'Yes' if has_past_context else 'No'}")
        if has_past_context:
            logger.info(f"   Past context size: {len(past_context)} characters")
            logger.info(f"   Bot is ready with agentic memory from {len(past_sessions)} past sessions")

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

        # Setup event handlers with transcript storage
        logger.info("Setting up event handlers (including session save on disconnect)...")
        await setup_event_handlers(transport, task, transcript_storage, user_name, ctx.room.name, context)
        logger.info("✅ Event handlers configured - session will be saved on disconnect")

        # Run pipeline
        logger.info("🚀 Starting pipeline runner - session is now active")
        logger.info(f"   User: {user_name}")
        logger.info(f"   Room: {ctx.room.name}")
        logger.info(f"   Supabase enabled: {settings.SUPABASE_ENABLED}")
        runner = PipelineRunner()
        await runner.run(task)
        logger.info("⏹️  Pipeline runner stopped")

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

