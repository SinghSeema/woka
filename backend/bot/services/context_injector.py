"""Context injection service for dynamically adding past session context."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.context_manager import estimate_tokens, truncate_summary

if TYPE_CHECKING:
    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

logger = get_logger(__name__)

# Maximum tokens for injected context (reserve space for conversation)
MAX_INJECTED_CONTEXT_TOKENS = 2000


def inject_past_context(
    context: "OpenAILLMContext",
    sessions: List[Dict[str, Any]],
    user_name: str,
    query_text: Optional[str] = None
) -> bool:
    """Inject retrieved past sessions into LLM context.
    
    Args:
        context: OpenAILLMContext instance
        sessions: List of session dictionaries to inject
        user_name: User's name for personalization
        query_text: Optional query text that triggered this injection
        
    Returns:
        True if injection was successful, False otherwise
    """
    if not sessions:
        logger.debug("No sessions to inject")
        return False
    
    injection_start_time = datetime.now()
    try:
        # Format sessions into context string
        context_text = _format_sessions_for_injection(sessions, user_name, query_text)
        
        # Estimate tokens
        estimated_tokens = estimate_tokens(context_text)
        
        if estimated_tokens > MAX_INJECTED_CONTEXT_TOKENS:
            logger.warning(
                f"Injected context too large: {estimated_tokens} tokens "
                f"(max: {MAX_INJECTED_CONTEXT_TOKENS}). Truncating..."
            )
            # Truncate sessions if needed
            context_text = _truncate_context(context_text, MAX_INJECTED_CONTEXT_TOKENS)
            estimated_tokens = estimate_tokens(context_text)

        # Debug: log compact preview of what we are about to inject
        injection_preview = context_text[:600].replace("\n", " ")
        logger.debug(
            f"[past-context] Final injected context preview "
            f"(sessions={len(sessions)}, tokens≈{estimated_tokens}, chars={len(context_text)}): "
            f"{injection_preview}"
        )
        
        # Inject as system message
        # Note: OpenAILLMContext may not support adding system messages mid-conversation
        # We'll add it as a user message with special formatting
        injection_message = {
            "role": "system",
            "content": context_text
        }
        
        # Try to add to context
        try:
            messages = context.get_messages()
            if not messages:
                logger.warning("No existing messages in context, cannot inject")
                return False
            
            # Find the primary system message (the one with the role description)
            # Prepending/Appending to the primary instruction is much more reliable
            # than adding separate system messages mid-stream.
            system_msg_index = -1
            for i, msg in enumerate(messages):
                if msg.get("role") == "system":
                    system_msg_index = i
                    break
            
            if system_msg_index >= 0:
                # Append to existing system prompt
                current_content = messages[system_msg_index].get("content", "")
                # Add a clear separator
                updated_content = current_content + "\n\n" + context_text
                messages[system_msg_index]["content"] = updated_content
                logger.info(f"✅ Appended past context to primary system prompt (total size: {len(updated_content)} chars)")
            else:
                # Fallback: Insert at beginning
                messages.insert(0, injection_message)
                logger.info("✅ Inserted new system message for past context")
            
            injection_duration = (datetime.now() - injection_start_time).total_seconds() * 1000
            logger.info(
                f"💉 Context injection: SUCCESS, sessions={len(sessions)}, "
                f"tokens={estimated_tokens} in {injection_duration:.0f}ms"
            )
                
        except Exception as e:
            logger.error(f"Error adding injection to context: {e}", exc_info=True)
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error injecting past context: {e}", exc_info=True)
        return False


def _format_sessions_for_injection(
    sessions: List[Dict[str, Any]],
    user_name: str,
    query_text: Optional[str] = None
) -> str:
    """Format sessions into context string for injection.
    
    Args:
        sessions: List of session dictionaries
        user_name: User's name
        query_text: Optional query that triggered this
        
    Returns:
        Formatted context string
    """
    context_parts = []
    
    if query_text:
        context_parts.append(
            f"## ADDITIONAL CONTEXT (Retrieved for: \"{query_text}\")\n"
        )
    else:
        context_parts.append("## ADDITIONAL CONTEXT (Retrieved Past Sessions)\n")
    
    # Make it explicit how the model should use this information.
    context_parts.append(
        "You have access to the following past session summaries. "
        "Treat them as ground truth about the user's prior sessions and use them "
        "to answer the current question.\n\n"
    )
    
    for i, session in enumerate(sessions, 1):
        summary = session.get("summary", "")
        created_at = session.get("created_at", "")
        duration = session.get("duration_seconds", 0)
        message_count = session.get("message_count", 0)
        similarity = session.get("similarity")
        
        # Format date
        date_str = "recent"
        date_display = "recently"
        if created_at:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                date_str = dt.strftime("%Y-%m-%d")
                date_display = dt.strftime("%B %d, %Y")
            except:
                date_str = created_at[:10] if len(created_at) >= 10 else "recent"
                date_display = date_str
        
        # Format duration
        duration_min = int(duration / 60) if duration else 0
        
        # Truncate summary if needed
        summary = truncate_summary(summary, max_length=settings.MAX_SUMMARY_LENGTH)
        
        context_parts.append(f"**Session {i}** - {date_display} ({date_str})\n")
        context_parts.append(f"Duration: {duration_min} minutes | Messages: {message_count}\n")
        if similarity is not None:
            context_parts.append(f"Relevance: {similarity:.1%}\n")
        context_parts.append(f"Summary: {summary}\n\n")
    
    context_parts.append(
        "Use this information to answer the user's question about past conversations.\n"
    )
    
    return "".join(context_parts)


def _truncate_context(context_text: str, max_tokens: int) -> str:
    """Truncate context text to fit within token limit.
    
    Args:
        context_text: Context text to truncate
        max_tokens: Maximum tokens allowed
        
    Returns:
        Truncated context text
    """
    # Simple truncation by characters (rough estimate)
    max_chars = max_tokens * 4  # ~4 chars per token
    
    if len(context_text) <= max_chars:
        return context_text
    
    # Truncate and add ellipsis
    truncated = context_text[:max_chars - 3] + "..."
    logger.debug(f"Truncated context from {len(context_text)} to {len(truncated)} characters")
    return truncated

