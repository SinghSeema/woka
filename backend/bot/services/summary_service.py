"""Session summary generation service."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def generate_session_summary(
    transcript: List[Dict[str, Any]], user_name: str, duration_seconds: float
) -> str:
    """Generate LLM-based session summary optimized for agentic memory context.

    Args:
        transcript: List of message dictionaries with role and content
        user_name: User's name
        duration_seconds: Session duration in seconds

    Returns:
        Comprehensive summary text optimized for future session context
    """
    try:
        # Filter out system messages and format transcript
        conversation = [
            f"{msg['role']}: {msg['content']}"
            for msg in transcript
            if msg.get("role") in ["user", "assistant"]
        ]

        if len(conversation) < 2:
            logger.warning("Not enough messages for summary generation")
            return _generate_basic_summary(user_name, duration_seconds)

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
                                "content": "You are an expert at creating comprehensive, context-rich summaries of wellness coaching conversations. Your summaries are used to help an AI coach remember past sessions and provide continuity. Focus on capturing specific details, goals, progress, and actionable information that would be valuable in future conversations.",
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
                logger.info(f"Generated LLM summary for {user_name}: {len(summary)} chars")
                return summary

        except Exception as e:
            logger.error(f"Error calling Groq API for summary: {e}", exc_info=True)
            return _generate_basic_summary(user_name, duration_seconds)

    except Exception as e:
        logger.error(f"Error generating session summary: {e}", exc_info=True)
        return _generate_basic_summary(user_name, duration_seconds)


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

