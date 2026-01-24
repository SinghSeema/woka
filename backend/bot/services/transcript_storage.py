"""In-memory transcript storage for sessions."""

import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.logging import get_logger

logger = get_logger(__name__)


class TranscriptStorage:
    """In-memory storage for session transcripts."""

    def __init__(self):
        """Initialize transcript storage."""
        self.messages: List[Dict[str, Any]] = []
        self.session_start: datetime = datetime.now()
        self.session_id: str = ""

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the transcript.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        self.messages.append(message)
        logger.debug(f"Added {role} message to transcript: {len(self.messages)} messages")

    def get_transcript(self) -> List[Dict[str, Any]]:
        """Get the full transcript.

        Returns:
            List of message dictionaries
        """
        return self.messages.copy()

    def get_duration_seconds(self) -> float:
        """Get session duration in seconds.

        Returns:
            Duration in seconds
        """
        duration = datetime.now() - self.session_start
        return duration.total_seconds()

    def get_message_count(self) -> int:
        """Get total message count.

        Returns:
            Number of messages
        """
        return len(self.messages)

    def clear_session(self) -> None:
        """Clear the transcript storage."""
        self.messages = []
        self.session_start = datetime.now()
        logger.debug("Transcript storage cleared")

    def set_session_id(self, session_id: str) -> None:
        """Set the session ID.

        Args:
            session_id: Unique session identifier
        """
        self.session_id = session_id

