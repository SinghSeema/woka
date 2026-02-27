"""Session summary generation service."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.topic_extractor import (
    extract_topics_from_user_messages,
    extract_topics_from_user_messages_hybrid
)
from bot.services.llm_topic_extractor import consolidate_topics

logger = get_logger(__name__)


async def generate_session_summary(
    transcript: List[Dict[str, Any]], user_name: str, duration_seconds: float,
    performance_monitor=None, room_name: str = ""
) -> Tuple[str, List[str]]:
    """Generate LLM-based session summary and extract topics.

    Args:
        transcript: List of message dictionaries with role and content
        user_name: User's name
        duration_seconds: Session duration in seconds
        performance_monitor: Optional performance monitor for tracking
        room_name: Optional room name for tracking

    Returns:
        Tuple of (summary_text, topics_list) where topics_list is extracted from summary
    """
    try:
        # Filter out system messages and format transcript
        conversation = [
            f"{msg['role']}: {msg['content']}"
            for msg in transcript
            if msg.get("role") in ["user", "assistant"]
        ]

        if len(conversation) < 2:
            summary = _generate_basic_summary(user_name, duration_seconds)
            # Extract topics from user messages only (not from summary)
            # Use hybrid extraction (keyword + LLM fallback if enabled)
            user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
            extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages)
            # Consolidate to 3-5 topics for cleaner storage
            topics = await consolidate_topics(extracted_topics, max_topics=5)
            return summary, topics

        # Use more messages for better context (last 30 messages or all if less)
        conversation_text = "\n".join(conversation[-30:]) if len(conversation) > 30 else "\n".join(conversation)
        
        # Calculate session duration in minutes
        minutes = int(duration_seconds / 60)
        seconds = int(duration_seconds % 60)

        # Enhanced summary prompt for better context
        summary_prompt = f"""Create a comprehensive summary of this wellness coaching session with {user_name} (duration: {minutes}m {seconds}s). 

The summary will be used as context in future sessions to provide continuity and personalized coaching. Make it detailed enough to help the coach remember:
- User's specific goals, concerns, and challenges mentioned
- Topics discussed (sleep, nutrition, exercise, stress, habits, etc.)
- Key advice, recommendations, or strategies provided
- User's progress, achievements, or setbacks mentioned
- Plans, commitments, or next steps discussed
- User's preferences, lifestyle, or constraints mentioned
- Any patterns or recurring themes

Format the summary as a concise but informative paragraph (4-6 sentences) that captures the essence of the conversation. Focus on actionable information that would be useful in future sessions.

Conversation transcript:
{conversation_text}

Comprehensive summary:"""

        # Use Groq LLM API directly for summarization
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert at creating comprehensive, context-rich summaries of wellness coaching conversations. Your summaries are used to help an AI coach remember past sessions and provide continuity. Focus on capturing specific details, goals, progress, and actionable information that would be valuable in future conversations. Always write summaries in English regardless of the language spoken in the conversation.",
                            },
                            {"role": "user", "content": summary_prompt},
                        ],
                        "temperature": 0.4,  # Slightly higher for more natural summaries
                        "max_tokens": 300,  # Increased for more comprehensive summaries
                    },
                )
                response.raise_for_status()
                result = response.json()
                summary = result["choices"][0]["message"]["content"].strip()
                
                # Extract token usage if available and track it
                usage = result.get("usage", {})
                if usage and performance_monitor and room_name:
                    performance_monitor.record_request(
                        user_name=user_name,
                        room_name=room_name,
                        request_type='llm_summary',
                        duration_ms=0,
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        success=True
                    )
                
                # Extract topics from USER MESSAGES ONLY (not from summary or assistant responses)
                # Use hybrid extraction (keyword + LLM fallback if enabled)
                user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
                extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages)
                # Ensure topics is always a list (never None)
                if extracted_topics is None:
                    extracted_topics = []
                
                # Consolidate topics to 3-5 high-level topics for cleaner storage
                # This prevents verbose topic lists while maintaining semantic search capability
                topics = await consolidate_topics(extracted_topics, max_topics=5)
                
                logger.info(
                    f"✅ [SESSION STORAGE] Summary: {len(summary)} chars | "
                    f"Topics: {len(extracted_topics)} extracted → {len(topics)} consolidated: {topics}"
                )
                
                return summary, topics

        except httpx.HTTPStatusError as e:
            logger.error(
                f"❌ [SESSION SUMMARY] HTTP error {e.response.status_code} | "
                f"Response: {e.response.text[:200] if hasattr(e.response, 'text') else 'N/A'}"
            )
            summary = _generate_basic_summary(user_name, duration_seconds)
            user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
            extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages)
            if extracted_topics is None:
                extracted_topics = []
            topics = await consolidate_topics(extracted_topics, max_topics=5)
            return summary, topics
        except httpx.TimeoutException:
            logger.warning("⚠️  [SESSION SUMMARY] Request timeout, using basic summary")
            summary = _generate_basic_summary(user_name, duration_seconds)
            user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
            extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages)
            if extracted_topics is None:
                extracted_topics = []
            topics = await consolidate_topics(extracted_topics, max_topics=5)
            return summary, topics
        except Exception as e:
            logger.error(
                f"❌ [SESSION SUMMARY] Error: {type(e).__name__}: {e}",
                exc_info=True
            )
            summary = _generate_basic_summary(user_name, duration_seconds)
            user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
            extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages)
            if extracted_topics is None:
                extracted_topics = []
            topics = await consolidate_topics(extracted_topics, max_topics=5)
            return summary, topics

    except Exception as e:
        logger.error(
            f"❌ [SESSION SUMMARY] Unexpected error: {type(e).__name__}: {e}",
            exc_info=True
        )
        summary = _generate_basic_summary(user_name, duration_seconds)
        user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
        extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages)
        if extracted_topics is None:
            extracted_topics = []
        topics = await consolidate_topics(extracted_topics, max_topics=5)
        return summary, topics


def _generate_basic_summary(user_name: str, duration_seconds: float) -> str:
    """Generate a basic summary as fallback.

    Args:
        user_name: User's name
        duration_seconds: Session duration

    Returns:
        Basic summary text
    """
    minutes = int(duration_seconds / 60)
    return f"Session with {user_name} lasted {minutes} minutes. Discussed wellness topics and received coaching guidance."

