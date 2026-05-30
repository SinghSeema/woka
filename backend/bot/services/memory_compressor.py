"""Memory compression and summarization for conversation history."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def summarize_conversation_segment(
    messages: List[Dict[str, Any]],
    user_name: str,
    previous_summary: Optional[str] = None
) -> Optional[str]:
    """Summarize a segment of conversation messages, optionally merging with previous summary.
    
    Args:
        messages: List of message dictionaries to summarize
        user_name: User's name for context
        previous_summary: Optional previous running summary to merge with
        
    Returns:
        Summary text or None if summarization fails
    """
    if not messages or len(messages) < 2:
        logger.warning("Not enough messages to summarize segment")
        return None
    
    try:
        # Format conversation for summarization
        conversation = [
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages
            if msg.get("role") in ["user", "assistant"]
        ]
        
        if len(conversation) < 2:
            return None
        
        conversation_text = "\n".join(conversation)
        
        # Use LLM to create a concise summary or merge with previous
        if previous_summary:
            summary = await _merge_summaries(previous_summary, conversation_text, user_name)
        else:
            summary = await _generate_llm_summary(conversation_text, user_name, len(messages))
        
        if summary:
            logger.info(f"✅ Processed memory compression for {len(messages)} messages")
        else:
            logger.warning("Failed to generate summary for conversation segment")
        
        return summary
        
    except Exception as e:
        logger.error(f"Error summarizing conversation segment: {e}", exc_info=True)
        return None


async def _merge_summaries(
    previous_summary: str,
    new_conversation_text: str,
    user_name: str
) -> Optional[str]:
    """Merge a new conversation segment into an existing structured summary."""
    try:
        import httpx

        merge_prompt = f"""You are maintaining a structured coaching memory for {user_name}.
Update each field below using the existing summary and the new conversation.

EXISTING SUMMARY:
{previous_summary}

NEW CONVERSATION SEGMENT:
{new_conversation_text}

Output ONLY the updated summary using this exact structure (one line per field, write "none" if not applicable):

GOAL: [current focus with specific metric if mentioned, e.g. "walk 30 min 3x/week"]
PROGRESS: [what has been done or current status]
COMMITMENTS: [specific actions {user_name} agreed to do before next session]
UNRESOLVED: [struggles or open questions that were not resolved]
CONSTRAINTS: [dislikes, busy times, equipment limits, or other restrictions mentioned]

Rules:
- PRESERVE information from existing fields unless the new conversation explicitly changes it.
- COMMITMENTS should be concrete actions, not vague intentions.
- UNRESOLVED should list open challenges that still need follow-up.
- Do NOT add explanations or extra text outside the five fields."""

        summary_model = getattr(settings, "SUMMARIZATION_MODEL", settings.LLM_MODEL)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": summary_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a wellness coaching memory assistant. Output only the structured summary fields — no extra text."
                        },
                        {"role": "user", "content": merge_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.error(f"Error merging summaries: {e}", exc_info=True)
        return previous_summary + "\nUNRESOLVED: [recent update failed, continuity preserved]"


async def _generate_llm_summary(
    conversation_text: str,
    user_name: str,
    message_count: int
) -> Optional[str]:
    """Generate a structured summary from raw conversation text."""
    try:
        import httpx

        # Keep last 3000 chars so the prompt stays within token budget
        if len(conversation_text) > 3000:
            conversation_text = conversation_text[-3000:]

        summary_prompt = f"""Summarize this wellness coaching conversation with {user_name} ({message_count} messages).
Extract each field below. Write "none" if the conversation does not mention it.

Conversation:
{conversation_text}

Output ONLY the five fields (no extra text):

GOAL: [current focus with specific metric if mentioned, e.g. "walk 30 min 3x/week"]
PROGRESS: [what has been done or current status]
COMMITMENTS: [specific actions {user_name} agreed to do before next session]
UNRESOLVED: [struggles or open questions that were not resolved]
CONSTRAINTS: [dislikes, busy times, equipment limits, or other restrictions mentioned]"""

        summary_model = getattr(settings, "SUMMARIZATION_MODEL", settings.LLM_MODEL)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": summary_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a wellness coaching memory assistant. Output only the structured summary fields — no extra text."
                        },
                        {"role": "user", "content": summary_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 250,
                },
            )
            response.raise_for_status()
            result = response.json()
            summary = result["choices"][0]["message"]["content"].strip()

            usage = result.get("usage", {})
            if usage:
                logger.debug(
                    f"Memory compression tokens: input={usage.get('prompt_tokens', 0)}, "
                    f"output={usage.get('completion_tokens', 0)}"
                )

            return summary

    except Exception as e:
        logger.error(f"Error generating LLM summary: {e}", exc_info=True)
        return _generate_basic_summary(conversation_text, message_count)


def _generate_basic_summary(conversation_text: str, message_count: int) -> str:
    """Generate a basic summary as fallback.
    
    Args:
        conversation_text: Conversation text
        message_count: Number of messages
        
    Returns:
        Basic summary text
    """
    # Extract first few words from conversation as basic summary
    preview = conversation_text[:200].replace("\n", " ")
    return f"Previous conversation segment ({message_count} messages): {preview}..."


def _format_structured_summary(summary: str) -> str:
    """Convert structured summary fields into natural coaching context prose.

    Strips "none" values and presents the remaining fields in a way the LLM
    can use naturally without seeing raw key/value syntax.
    """
    _FIELDS = ["GOAL", "PROGRESS", "COMMITMENTS", "UNRESOLVED", "CONSTRAINTS"]
    _LABELS = {
        "GOAL":        "Current goal",
        "PROGRESS":    "Progress so far",
        "COMMITMENTS": "What the user committed to do",
        "UNRESOLVED":  "Open challenges / unresolved",
        "CONSTRAINTS": "User constraints and preferences",
    }

    lines = []
    for field in _FIELDS:
        # Match "FIELD: value" (case-insensitive, tolerant of whitespace)
        import re
        match = re.search(rf"^{field}:\s*(.+)$", summary, re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if value.lower() not in ("none", "n/a", "-", ""):
                lines.append(f"- **{_LABELS[field]}**: {value}")

    if lines:
        return "\n".join(lines)

    # Fallback: return raw summary if it doesn't use the structured format
    return summary


def inject_summary_into_context(
    context,
    summary: str,
    message_range: Tuple[int, int]
) -> bool:
    """Inject a summary into the LLM context, replacing any existing running summary.
    
    Args:
        context: OpenAILLMContext instance
        summary: Summary text to inject
        message_range: Tuple of (start, end) message indices that were summarized
        
    Returns:
        True if injection was successful
    """
    try:
        messages = context.get_messages()

        # Debug: preview of the running summary we are about to inject
        summary_preview = summary[:600].replace("\n", " ")
        logger.debug(
            f"[memory-compression] Injecting running summary preview "
            f"(chars={len(summary)}): {summary_preview}"
        )
        
        # Look for existing running summary to replace
        summary_index = -1
        for i, msg in enumerate(messages):
            if msg.get("role") == "system" and "RUNNING CONVERSATION SUMMARY" in msg.get("content", ""):
                summary_index = i
                break
        
        # Format structured summary fields into readable coaching context
        summary_content = (
            "## RUNNING CONVERSATION SUMMARY\n"
            + _format_structured_summary(summary)
            + "\n\nThis is a compressed representation of the conversation history to maintain continuity while staying within token limits."
        )
        
        if summary_index >= 0:
            # Replace existing
            messages[summary_index]["content"] = summary_content
            logger.info(f"✅ Updated existing running summary in context")
        else:
            # Insert new summary after the initial system prompt
            insert_pos = 1
            for i, msg in enumerate(messages):
                if msg.get("role") == "system":
                    insert_pos = i + 1
            
            messages.insert(insert_pos, {
                "role": "system",
                "content": summary_content
            })
            logger.info(f"✅ Injected new running summary into context")
        
        return True
        
    except Exception as e:
        logger.error(f"Error injecting summary into context: {e}", exc_info=True)
        return False


def remove_old_messages(
    context,
    messages_to_remove: List[Dict[str, Any]]
) -> int:
    """Remove old messages from context.
    
    Args:
        context: OpenAILLMContext instance
        messages_to_remove: List of messages to remove
        
    Returns:
        Number of messages removed
    """
    try:
        messages = context.get_messages()
        
        # Create set of message content for fast lookup
        to_remove_content = {
            (msg.get("role"), msg.get("content", ""))
            for msg in messages_to_remove
        }
        
        # Remove matching messages
        original_count = len(messages)
        messages[:] = [
            msg for msg in messages
            if (msg.get("role"), msg.get("content", "")) not in to_remove_content
        ]
        
        removed = original_count - len(messages)
        
        if removed > 0:
            logger.info(f"🗑️  Removed {removed} old messages from context")
        
        return removed
        
    except Exception as e:
        logger.error(f"Error removing old messages: {e}", exc_info=True)
        return 0

