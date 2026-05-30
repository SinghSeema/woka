"""Conversation memory management for long sessions."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.context_manager import estimate_tokens

logger = get_logger(__name__)


class ConversationMemory:
    """Manages conversation memory for long sessions."""
    
    def __init__(self):
        """Initialize conversation memory manager."""
        self.last_summary_message_count = 0
        self.summaries: List[Dict[str, Any]] = []  # Rolling summaries
        self.running_summary: Optional[str] = None  # Single accumulated summary
        self.last_check: Optional[datetime] = None
        self.compression_depth: int = 0  # How many incremental merges have happened
        
    def should_summarize(
        self,
        message_count: int,
        total_tokens: Optional[int] = None,
        context_window: int = 128000
    ) -> bool:
        """Check if conversation should be summarized.
        
        Args:
            message_count: Current number of messages in conversation
            total_tokens: Estimated total tokens (optional, calculated if None)
            context_window: Model context window size
            
        Returns:
            True if summarization should be triggered
        """
        if not getattr(settings, 'ENABLE_CONVERSATION_MEMORY', True):
            return False
        
        # Check message count threshold
        threshold = getattr(settings, 'MEMORY_SUMMARIZATION_THRESHOLD', 50)
        messages_since_last = message_count - self.last_summary_message_count
        
        if messages_since_last >= getattr(settings, 'MEMORY_SUMMARY_FREQUENCY', 25):
            logger.info(
                f"📊 Memory check: {message_count} messages, "
                f"{messages_since_last} since last summary - threshold: {threshold}"
            )
            return True
        
        # Check token usage threshold if available
        if total_tokens:
            warning_threshold = int(context_window * getattr(settings, 'CONTEXT_WARNING_THRESHOLD', 0.8))
            if total_tokens > warning_threshold:
                logger.warning(
                    f"⚠️  Context window usage high: {total_tokens}/{context_window} tokens "
                    f"({total_tokens/context_window*100:.1f}%)"
                )
                return True
        
        return False
    
    def get_messages_to_summarize(
        self,
        messages: List[Dict[str, Any]],
        keep_recent: int = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Split messages into those to summarize and those to keep.
        
        Args:
            messages: All conversation messages
            keep_recent: Number of recent messages to keep (defaults to config)
            
        Returns:
            Tuple of (messages_to_summarize, messages_to_keep)
        """
        if keep_recent is None:
            keep_recent = getattr(settings, 'MEMORY_KEEP_RECENT', 30)
        
        # Filter out system messages for summarization
        conversation_messages = [
            msg for msg in messages
            if msg.get("role") in ["user", "assistant"]
        ]
        
        if len(conversation_messages) <= keep_recent:
            # Not enough messages to summarize
            return [], conversation_messages
        
        # Split: older messages to summarize, recent ones to keep
        to_summarize = conversation_messages[:-keep_recent]
        to_keep = conversation_messages[-keep_recent:]
        
        logger.info(
            f"📝 Memory split: {len(to_summarize)} messages to summarize, "
            f"{len(to_keep)} messages to keep"
        )
        
        return to_summarize, to_keep
    
    def record_summarization(self, message_count: int, was_merge: bool = False) -> None:
        """Record that summarization was performed.

        Args:
            message_count: Current message count when summary was created
            was_merge: True if this was an incremental merge (depth increases),
                       False if it was a full re-summary from raw transcript (depth resets)
        """
        self.last_summary_message_count = message_count
        self.last_check = datetime.now()
        if was_merge:
            self.compression_depth += 1
        else:
            self.compression_depth = 0
        logger.debug(
            f"Recorded summarization at {message_count} messages "
            f"(depth={self.compression_depth}, merge={was_merge})"
        )

    @property
    def needs_full_resummary(self) -> bool:
        """True when incremental merges have stacked up enough to risk drift."""
        max_depth = getattr(settings, "MEMORY_MAX_COMPRESSION_DEPTH", 2)
        return self.compression_depth >= max_depth
    
    def add_rolling_summary(self, summary: str, message_range: Tuple[int, int]) -> None:
        """Add a rolling summary to track.
        
        Args:
            summary: Summary text
            message_range: Tuple of (start_message_index, end_message_index)
        """
        self.summaries.append({
            "summary": summary,
            "range": message_range,
            "created_at": datetime.now().isoformat()
        })
        logger.debug(f"Added rolling summary for messages {message_range[0]}-{message_range[1]}")
    
    def get_rolling_summaries(self) -> List[Dict[str, Any]]:
        """Get all rolling summaries.
        
        Returns:
            List of summary dictionaries
        """
        return self.summaries.copy()


def monitor_conversation_memory(
    context,
    memory_manager: ConversationMemory
) -> Dict[str, Any]:
    """Monitor conversation memory and return status.
    
    Args:
        context: OpenAILLMContext instance
        memory_manager: ConversationMemory instance
        
    Returns:
        Dictionary with memory status information
    """
    try:
        messages = context.get_messages()
        message_count = len([m for m in messages if m.get("role") in ["user", "assistant"]])
        
        # Estimate tokens for conversation history
        conversation_text = "\n".join([
            f"{m.get('role')}: {m.get('content', '')[:100]}"
            for m in messages[-50:]  # Sample last 50 for estimation
        ])
        estimated_tokens = estimate_tokens(conversation_text)
        
        # Full estimation (rough)
        full_estimated = estimate_tokens("\n".join([
            f"{m.get('role')}: {m.get('content', '')}"
            for m in messages
            if m.get("role") in ["user", "assistant"]
        ]))
        
        status = {
            "message_count": message_count,
            "estimated_tokens": full_estimated,
            "should_summarize": memory_manager.should_summarize(message_count, full_estimated),
            "last_summary_at": memory_manager.last_summary_message_count,
            "messages_since_summary": message_count - memory_manager.last_summary_message_count,
            "rolling_summaries_count": len(memory_manager.summaries)
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Error monitoring conversation memory: {e}", exc_info=True)
        return {
            "message_count": 0,
            "estimated_tokens": 0,
            "should_summarize": False,
            "error": str(e)
        }

