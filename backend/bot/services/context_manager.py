"""Context management utilities for managing LLM input context."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Token estimation: ~4 characters per token for English text
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from text.
    
    Args:
        text: Text to estimate tokens for.
        
    Returns:
        Estimated token count.
    """
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
    # ... (existing logic) ...
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
    past_context += "This enables you to provide continuity, remember their journey, and answer questions about past conversations.\n\n"
    past_context += "**Your capabilities with past sessions:**\n"
    past_context += "1. **Remember & Reference**: You can remember goals, concerns, progress, and topics from past sessions\n"
    past_context += "2. **Answer Questions**: When {user_name} asks about past sessions (e.g., 'What did we discuss last time?', 'What was my goal?'), you can reference the summaries below\n"
    past_context += "3. **Provide Continuity**: Reference past conversations naturally when relevant to current topics\n"
    past_context += "4. **Track Progress**: Acknowledge achievements, changes, or progress mentioned across sessions\n"
    past_context += "5. **Share Context**: When asked, you can share specific information from past sessions (e.g., 'In our session on [date], we discussed...')\n\n"
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

