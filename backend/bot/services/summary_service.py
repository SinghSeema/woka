"""Session summary generation service."""

import re
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

_METADATA_FIELDS = ["GOAL", "PROGRESS", "COMMITMENTS", "UNRESOLVED", "CONSTRAINTS"]


def _parse_dual_response(raw: str) -> Tuple[str, Dict[str, str]]:
    """Split a dual-format LLM response into prose summary and metadata dict.

    Expected format (LLM is instructed to use this):
        PROSE_SUMMARY:
        <paragraph>

        STRUCTURED:
        GOAL: <value>
        PROGRESS: <value>
        COMMITMENTS: <value>
        UNRESOLVED: <value>
        CONSTRAINTS: <value>

    Returns (prose, metadata_dict). Falls back gracefully if format is missing.
    """
    prose = raw.strip()
    metadata: Dict[str, str] = {}

    if "STRUCTURED:" in raw:
        parts = raw.split("STRUCTURED:", 1)
        prose_block = parts[0]
        structured_block = parts[1]

        # Extract prose — remove "PROSE_SUMMARY:" header if present
        prose = re.sub(r"(?i)^PROSE_SUMMARY:\s*", "", prose_block.strip()).strip()

        # Extract each field from the structured block
        for field in _METADATA_FIELDS:
            match = re.search(
                rf"^{field}:\s*(.+)$", structured_block, re.IGNORECASE | re.MULTILINE
            )
            if match:
                value = match.group(1).strip()
                if value.lower() not in ("none", "n/a", "-", ""):
                    metadata[field.lower()] = value

    return prose, metadata


async def generate_session_summary(
    transcript: List[Dict[str, Any]], user_name: str, duration_seconds: float,
    performance_monitor=None, room_name: str = ""
) -> Tuple[str, List[str], Dict[str, str]]:
    """Generate LLM-based session summary and extract topics + structured metadata.

    Args:
        transcript: List of message dictionaries with role and content
        user_name: User's name
        duration_seconds: Session duration in seconds
        performance_monitor: Optional performance monitor for tracking
        room_name: Optional room name for tracking

    Returns:
        Tuple of (summary_text, topics_list, metadata_dict)
        metadata_dict keys: goal, progress, commitments, unresolved, constraints
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
            user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
            extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages)
            topics = await consolidate_topics(extracted_topics, max_topics=5)
            return summary, topics, {}

        # Use more messages for better context (last 30 messages or all if less)
        conversation_text = "\n".join(conversation[-30:]) if len(conversation) > 30 else "\n".join(conversation)
        
        # Calculate session duration in minutes
        minutes = int(duration_seconds / 60)
        seconds = int(duration_seconds % 60)

        # Dual-format prompt: prose summary for semantic search + structured fields for recall
        summary_prompt = f"""You are summarizing a wellness coaching session with {user_name} (duration: {minutes}m {seconds}s).

Respond in this EXACT format — two sections separated by "STRUCTURED:":

PROSE_SUMMARY:
<4-6 sentence paragraph capturing: goals discussed, advice given, progress reported, plans or commitments made, user preferences or constraints, and recurring themes. Write in third person. This will be used for semantic search in future sessions.>

STRUCTURED:
GOAL: <current focus with specific metric if mentioned, e.g. "sleep by 10 PM daily"; write "none" if not mentioned>
PROGRESS: <what {user_name} reported doing or achieving; write "none" if not mentioned>
COMMITMENTS: <specific actions {user_name} agreed to do before next session; write "none" if not mentioned>
UNRESOLVED: <struggles or open questions that were not resolved; write "none" if not mentioned>
CONSTRAINTS: <dislikes, busy times, equipment limits, or lifestyle restrictions mentioned; write "none" if not mentioned>

Conversation transcript:
{conversation_text}"""

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
                raw_output = result["choices"][0]["message"]["content"].strip()

                # Parse dual-format response into prose + structured metadata
                summary, metadata = _parse_dual_response(raw_output)

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

                user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
                extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages) or []
                topics = await consolidate_topics(extracted_topics, max_topics=5)

                logger.info(
                    f"✅ [SESSION STORAGE] Summary: {len(summary)} chars | "
                    f"Topics: {len(extracted_topics)} → {len(topics)}: {topics} | "
                    f"Metadata fields: {list(metadata.keys())}"
                )

                return summary, topics, metadata

        except httpx.HTTPStatusError as e:
            logger.error(
                f"❌ [SESSION SUMMARY] HTTP error {e.response.status_code} | "
                f"Response: {e.response.text[:200] if hasattr(e.response, 'text') else 'N/A'}"
            )
            summary = _generate_basic_summary(user_name, duration_seconds)
            user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
            extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages) or []
            topics = await consolidate_topics(extracted_topics, max_topics=5)
            return summary, topics, {}
        except httpx.TimeoutException:
            logger.warning("⚠️  [SESSION SUMMARY] Request timeout, using basic summary")
            summary = _generate_basic_summary(user_name, duration_seconds)
            user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
            extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages) or []
            topics = await consolidate_topics(extracted_topics, max_topics=5)
            return summary, topics, {}
        except Exception as e:
            logger.error(
                f"❌ [SESSION SUMMARY] Error: {type(e).__name__}: {e}",
                exc_info=True
            )
            summary = _generate_basic_summary(user_name, duration_seconds)
            user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
            extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages) or []
            topics = await consolidate_topics(extracted_topics, max_topics=5)
            return summary, topics, {}

    except Exception as e:
        logger.error(
            f"❌ [SESSION SUMMARY] Unexpected error: {type(e).__name__}: {e}",
            exc_info=True
        )
        summary = _generate_basic_summary(user_name, duration_seconds)
        user_messages = [msg.get("content", "") for msg in transcript if msg.get("role") == "user"]
        extracted_topics = await extract_topics_from_user_messages_hybrid(user_messages) or []
        topics = await consolidate_topics(extracted_topics, max_topics=5)
        return summary, topics, {}


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

