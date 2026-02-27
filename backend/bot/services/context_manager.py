"""Context management utilities for managing LLM input context."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional


from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Token estimation — uses tiktoken when available, falls back to char ratio
CHARS_PER_TOKEN = 4

try:
    import tiktoken
    _tokenizer = tiktoken.get_encoding("cl100k_base")  # Compatible with most modern LLMs
    _HAS_TIKTOKEN = True
except Exception:
    _tokenizer = None
    _HAS_TIKTOKEN = False


def estimate_tokens(text: str) -> int:
    """Estimate token count from text.
    
    Uses tiktoken for accuracy when available, falls back to char/4 ratio.
    
    Args:
        text: Text to estimate tokens for.
        
    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    if _HAS_TIKTOKEN and _tokenizer:
        try:
            return len(_tokenizer.encode(text))
        except Exception:
            pass
    return len(text) // CHARS_PER_TOKEN


def truncate_summary(summary: str, max_length: int = None) -> str:
    """Truncate a session summary to maximum length.
    
    Args:
        summary: Summary text to truncate.
        max_length: Maximum length in characters. Defaults to settings.MAX_SUMMARY_LENGTH.
        
    Returns:
        Truncated summary.
    """
    if max_length is None:
        max_length = settings.MAX_SUMMARY_LENGTH
    
    if len(summary) <= max_length:
        return summary
    
    return summary[:max_length - 3] + "..."


def truncate_past_sessions(
    past_sessions: List[Dict[str, Any]],
    max_sessions: int = None,
    max_total_size: int = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Truncate past sessions list to fit within limits.
    
    Args:
        past_sessions: List of past session dictionaries.
        max_sessions: Maximum number of sessions to include. Defaults to settings.MAX_PAST_SESSIONS.
        max_total_size: Maximum total size in characters. Defaults to settings.MAX_PAST_CONTEXT_SIZE.
        
    Returns:
        Tuple of (truncated_sessions, total_size)
    """
    if max_sessions is None:
        max_sessions = settings.MAX_PAST_SESSIONS
    if max_total_size is None:
        max_total_size = settings.MAX_PAST_CONTEXT_SIZE
    
    # First, limit by number of sessions
    sessions = past_sessions[:max_sessions]
    
    # Truncate summaries if needed
    total_size = 0
    truncated_sessions = []
    
    for session in sessions:
        summary = session.get("summary", "")
        truncated_summary = truncate_summary(summary)
        session_copy = session.copy()
        session_copy["summary"] = truncated_summary
        
        # Estimate size of this session's context (summary + metadata)
        session_size = len(truncated_summary) + 200  # ~200 chars for metadata/formatting
        
        # If adding this session would exceed limit, stop
        if total_size + session_size > max_total_size and truncated_sessions:
            logger.warning(
                f"Past context size limit reached. Including {len(truncated_sessions)} sessions "
                f"instead of {len(sessions)}"
            )
            break
        
        truncated_sessions.append(session_copy)
        total_size += session_size
    
    return truncated_sessions, total_size


def validate_context_size(
    system_prompt: str,
    past_context: str = "",
    model_context_window: int = 128000,
    base_system_prompt: str = None
) -> Tuple[bool, Optional[str]]:
    """Validate context sizes and return warnings.
    
    Args:
        system_prompt: Total system prompt text (base + past_context).
        past_context: Past session context text.
        model_context_window: Model's context window size in tokens.
        base_system_prompt: Base system prompt without past_context (optional, calculated if not provided).
        
    Returns:
        Tuple of (is_valid, warning_message). warning_message is None if valid.
    """
    total_tokens = estimate_tokens(system_prompt)
    past_tokens = estimate_tokens(past_context) if past_context else 0

    warning_threshold = int(model_context_window * settings.CONTEXT_WARNING_THRESHOLD)
    error_threshold = model_context_window  # hard limit

    if total_tokens >= error_threshold:
        return False, (
            f"System prompt too large: {total_tokens} tokens "
            f"exceeds model context window of {error_threshold} tokens."
        )

    if total_tokens >= warning_threshold:
        return True, (
            f"System prompt approaching context limit: {total_tokens}/{warning_threshold} tokens "
            f"({100 * total_tokens // model_context_window}% of context window used)."
        )

    if past_tokens > settings.MAX_PAST_CONTEXT_SIZE // CHARS_PER_TOKEN:
        return True, (
            f"Past context is large: {past_tokens} tokens — consider reducing MAX_PAST_SESSIONS."
        )

    return True, None


def prune_context_if_needed(
    messages: List[Dict[str, Any]],
    max_tokens: int = 4000,
    keep_recent: int = 10
) -> Tuple[List[Dict[str, Any]], bool]:
    """Prune conversation messages if they exceed token limits.
    
    This is a safety measure to prevent TPD limit overflows or 400 errors.
    It removes middle messages while keeping system prompt and most recent ones.
    
    Args:
        messages: Current list of messages
        max_tokens: Maximum allowed tokens for conversation history
        keep_recent: Number of recent messages to always keep
        
    Returns:
        Tuple of (pruned_messages, was_pruned)
    """
    try:
        # Estimate total tokens for user/assistant messages
        history_messages = [m for m in messages if m.get("role") in ["user", "assistant"]]
        if not history_messages:
            return messages, False
            
        history_text = "\n".join([m.get("content", "") for m in history_messages])
        total_tokens = estimate_tokens(history_text)
        
        if total_tokens <= max_tokens:
            return messages, False
            
        logger.warning(f"⚠️  Context pruning triggered: {total_tokens} tokens > {max_tokens} limit")
        
        # Keep system messages (usually index 0, but could be more)
        system_messages = [m for m in messages if m.get("role") == "system"]
        
        # Keep the 'keep_recent' most recent user/assistant messages
        recent_messages = history_messages[-keep_recent:]
        
        # If still over limit with just recent, we have to truncate them (rare)
        # Otherwise, the middle part is gone
        pruned_messages = system_messages + [{"role": "system", "content": "... [older messages pruned to save tokens] ..."}] + recent_messages
        
        return pruned_messages, True
        
    except Exception as e:
        logger.error(f"Error pruning context: {e}")
        return messages, False


def build_past_context(
    past_sessions: List[Dict[str, Any]],
    user_name: str
) -> Tuple[str, int]:
    """Build past session context string from session list.
    
    Args:
        past_sessions: List of past session dictionaries.
        user_name: User's name for personalization.
        
    Returns:
        Tuple of (past_context_string, number_of_sessions_included)
    """
    if not past_sessions:
        return "", 0
    
    # Truncate sessions to fit within limits
    truncated_sessions, _ = truncate_past_sessions(past_sessions)
    
    if not truncated_sessions:
        return "", 0
    
    logger.debug(f"📝 Building past context from {len(truncated_sessions)} sessions")
    
    past_context = "\n\n## PAST SESSIONS CONTEXT (Agentic Memory)\n"
    past_context += f"You have access to summaries from {len(truncated_sessions)} recent sessions with {user_name}. "
    past_context += "Use this information to answer their specific questions about past conversations.\n\n"
    past_context += "**IMPORTANT - Focus on User's Query:**\n"
    past_context += f"- When {user_name} asks a question, focus your answer specifically on what they asked about\n"
    past_context += "- Do not provide generic information or topics they didn't ask about\n"
    past_context += "- Reference past sessions only when directly relevant to their current question\n"
    past_context += "- Be precise and relevant - avoid broad, generic responses\n\n"
    past_context += "**Your capabilities with past sessions:**\n"
    past_context += f"1. **Answer Specific Questions**: When {user_name} asks about past sessions, reference the relevant information from summaries below\n"
    past_context += "2. **Be Precise**: Only mention topics, goals, or information that directly relates to their question\n"
    past_context += "3. **Provide Continuity**: Reference past conversations naturally when relevant to current topics\n"
    past_context += "4. **Track Progress**: Acknowledge achievements or progress when specifically asked about it\n\n"
    past_context += "**Recent session summaries (most recent first):**\n\n"
    
    for i, session in enumerate(truncated_sessions, 1):
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
                date_display = dt.strftime("%B %d, %Y")
            except:
                date_str = created_at[:10] if len(created_at) >= 10 else "recent"
                date_display = date_str
        
        # Format duration
        duration_min = int(duration / 60) if duration else 0
        
        past_context += f"**Session {i}** - {date_display} ({date_str})\n"
        past_context += f"Duration: {duration_min} minutes | Messages: {message_count}\n"
        past_context += f"Summary: {summary}\n\n"
    
    past_context += "**Guidelines for using past context:**\n"
    past_context += f"- **Focus on the query**: When {user_name} asks a question, answer it directly using relevant information from the summaries\n"
    past_context += f"- **Be specific**: If {user_name} asks about a specific topic (e.g., 'zumba'), only discuss that topic, not generic related topics\n"
    past_context += "- **Avoid generic terms**: Don't extract or mention generic wellness topics unless the user specifically asked about them\n"
    past_context += "- **Precision over breadth**: Better to give a focused answer about what they asked than a broad answer covering many topics\n"
    past_context += "- **When topics connect**: Naturally reference past conversations only when directly relevant (e.g., 'Last time you mentioned zumba classes...')\n"
    past_context += "- **Don't force it**: Only reference past sessions when it directly answers their question\n"
    past_context += f"- **Answer the question**: If {user_name} asks 'What did we discuss about [topic]?', find and share ONLY information about that specific topic from the summaries\n"
    
    return past_context, len(truncated_sessions)


def handle_query_failure(
    error: Exception,
    query_type: str,
    user_name: str,
    fallback_sessions: List[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Handle Supabase query failures with graceful fallback.
    
    Args:
        error: The exception that occurred
        query_type: Type of query that failed (e.g., 'semantic', 'date', 'topic')
        user_name: User's name
        fallback_sessions: Optional pre-loaded sessions to use as fallback
        
    Returns:
        List of sessions (fallback or empty)
    """
    logger.error(
        f"❌ Query failure ({query_type}) for {user_name}: {error}",
        exc_info=True
    )
    
    if fallback_sessions:
        logger.info(f"🔄 Using {len(fallback_sessions)} pre-loaded sessions as fallback")
        return fallback_sessions
    
    logger.warning(f"⚠️  No fallback available, returning empty results")
    return []


def validate_injected_context_size(
    context_text: str,
    max_tokens: int = 2000
) -> Tuple[bool, Optional[str]]:
    """Validate size of context to be injected.
    
    Args:
        context_text: Context text to validate
        max_tokens: Maximum tokens allowed
        
    Returns:
        Tuple of (is_valid, warning_message)
    """
    estimated_tokens = estimate_tokens(context_text)
    
    if estimated_tokens > max_tokens * 1.2:  # 20% over limit
        return False, f"Injected context too large: {estimated_tokens} tokens (max: {max_tokens})"
    
    if estimated_tokens > max_tokens:
        return True, f"Injected context exceeds recommended size: {estimated_tokens} tokens (recommended: {max_tokens})"
    
    return True, None


def handle_intent_detection_fallback(
    user_message: str,
    original_intent_failed: bool = False
) -> Dict[str, Any]:
    """Handle intent detection failures with keyword fallback.
    
    Args:
        user_message: User's message
        original_intent_failed: Whether original intent detection failed
        
    Returns:
        Dict with fallback intent information
    """
    if original_intent_failed:
        logger.warning("Intent detection failed, using keyword fallback")
    
    # Simple keyword-based fallback
    message_lower = user_message.lower()
    
    # Check for common past reference keywords
    keywords = ['past', 'before', 'last time', 'previous', 'earlier', 'ago']
    has_keyword = any(kw in message_lower for kw in keywords)
    
    if has_keyword:
        logger.info("Fallback: Detected past reference via keywords")
        return {
            "has_intent": True,
            "intent_type": "general",
            "confidence": 0.5,
            "query_text": user_message
        }
    
    return {
        "has_intent": False,
        "confidence": 0.0
    }


def log_query_metrics(
    query_type: str,
    duration_seconds: float,
    results_count: int,
    cache_hit: bool = False,
    user_name: str = None
) -> None:
    """Log query performance metrics.
    
    Args:
        query_type: Type of query (semantic, date, topic, etc.)
        duration_seconds: Query duration in seconds
        results_count: Number of results returned
        cache_hit: Whether this was a cache hit
        user_name: Optional user name for context
    """
    cache_status = "HIT" if cache_hit else "MISS"
    logger.info(
        f"📊 Query metrics: type={query_type}, duration={duration_seconds:.3f}s, "
        f"results={results_count}, cache={cache_status}"
        + (f", user={user_name}" if user_name else "")
    )
    
    # Log slow queries
    if duration_seconds > 2.0:
        logger.warning(f"⚠️  Slow query detected: {duration_seconds:.3f}s for {query_type}")


def log_context_injection(
    sessions_count: int,
    tokens_estimated: int,
    success: bool,
    user_name: str = None
) -> None:
    """Log context injection events.
    
    Args:
        sessions_count: Number of sessions injected
        tokens_estimated: Estimated tokens injected
        success: Whether injection was successful
        user_name: Optional user name for context
    """
    status = "✅ SUCCESS" if success else "❌ FAILED"
    logger.info(
        f"💉 Context injection: {status}, sessions={sessions_count}, "
        f"tokens={tokens_estimated}"
        + (f", user={user_name}" if user_name else "")
    )

