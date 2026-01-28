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
    """Merge a new conversation segment into an existing summary.
    
    Args:
        previous_summary: The existing running summary
        new_conversation_text: The new conversation text to add
        user_name: User's name
        
    Returns:
        Merged summary text
    """
    try:
        import httpx
        
        merge_prompt = f"""You are maintaining a 'Running Summary' of a wellness coaching journey for {user_name}.
Update the existing summary by incorporating the new conversation segment below.

EXISTING SUMMARY:
{previous_summary}

NEW CONVERSATION SEGMENT:
{new_conversation_text}

STRICT REQUIREMENTS for the UPDATED SUMMARY:
1. PRESERVE key progress, active goals, and established habits from the existing summary.
2. INCORPORATE any new goals, action steps, or insights from the new segment.
3. REMOVE redundant or outdated information to keep it concise.
4. Keep the total length under 4-5 sentences.

Updated Running Summary:"""

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
                            "content": "You are a wellness coaching memory assistant responsible for maintaining a concise running summary of a user's progress."
                        },
                        {"role": "user", "content": merge_prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 250,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
            
    except Exception as e:
        logger.error(f"Error merging summaries: {e}", exc_info=True)
        return previous_summary + "\n[Recent update failed, but continuity preserved]"


async def _generate_llm_summary(
    conversation_text: str,
    user_name: str,
    message_count: int
) -> Optional[str]:
    """Generate summary using LLM.
    
    Args:
        conversation_text: Formatted conversation text
        user_name: User's name
        message_count: Number of messages being summarized
        
    Returns:
        Summary text or None
    """
    try:
        import httpx
        
        # Truncate if too long (keep last 3000 chars for context to get better summaries)
        if len(conversation_text) > 3000:
            conversation_text = conversation_text[-3000:]
        
        # Enhanced coaching-specific prompt for better continuity
        summary_prompt = f"""Summarize this wellness coaching session segment with {user_name} ({message_count} messages).
The goal is to maintain continuity in their coaching journey.

STRICT REQUIREMENTS:
1. Identify the CURRENT FOCUS or HABIT being discussed.
2. Note any specific GOALS or ACTION STEPS agreed upon.
3. Capture the USER'S EMOTIONAL STATE or ENERGY LEVEL if mentioned.
4. Keep the summary under 3 sentences.

Conversation to summarize:
{conversation_text}

Concise Coaching Summary:"""

        # Use the specific summarization model to save TPD on the main model
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
                            "content": "You are a wellness coaching memory assistant. Your job is to extract key coaching state to ensure continuity across session segments."
                        },
                        {"role": "user", "content": summary_prompt},
                    ],
                    "temperature": 0.1,  # Lower temperature for more consistent, factual summaries
                    "max_tokens": 150,
                },
            )
            response.raise_for_status()
            result = response.json()
            summary = result["choices"][0]["message"]["content"].strip()
            
            # Log token usage if available (for monitoring)
            usage = result.get("usage", {})
            if usage:
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                logger.debug(
                    f"Memory compression tokens: input={input_tokens}, output={output_tokens}"
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
        
        # Create summary message
        summary_content = f"## RUNNING CONVERSATION SUMMARY\n{summary}\n\nThis is a compressed representation of the conversation history to maintain continuity while staying within token limits."
        
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

