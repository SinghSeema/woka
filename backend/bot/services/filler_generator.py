"""Filler generation service for hiding latency during context queries.

When a cache miss occurs and we need to query the database, we generate
a natural filler utterance to buy time (1-2 seconds) while the query runs.
This makes the latency feel natural rather than awkward silence.
"""

import sys
from pathlib import Path
from typing import Optional
import random

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.logging import get_logger

logger = get_logger(__name__)


# Filler phrases organized by intent type
FILLERS_BY_INTENT = {
    "general": [
        "Let me check that for you...",
        "One moment, let me look that up...",
        "Sure, let me find that information...",
        "Let me see what I can find...",
        "Give me a second to check...",
    ],
    "date": [
        "Let me look back at those dates...",
        "Checking those dates for you...",
        "Let me find sessions from that time...",
        "Looking up sessions from that period...",
    ],
    "topic": [
        "Let me search for that topic...",
        "Finding sessions about that...",
        "Let me look for discussions on that...",
        "Searching for that topic...",
    ],
    "semantic": [
        "Let me think about that...",
        "Let me recall what we discussed...",
        "Let me search my memory...",
        "Let me find relevant information...",
    ],
}


def generate_filler(intent_type: str = "general", user_name: Optional[str] = None) -> str:
    """Generate a natural filler utterance.
    
    Args:
        intent_type: Type of intent (general, date, topic, semantic)
        user_name: Optional user name for personalization
        
    Returns:
        Filler text to say while querying
    """
    fillers = FILLERS_BY_INTENT.get(intent_type, FILLERS_BY_INTENT["general"])
    filler = random.choice(fillers)
    
    # Personalize if user name provided
    if user_name:
        # Sometimes add user name for warmth
        if random.random() < 0.3:  # 30% chance
            filler = f"{user_name}, {filler.lower()}"
    
    logger.debug(f"Generated filler for intent '{intent_type}': {filler}")
    return filler


def should_use_filler(query_duration_estimate: float = 0.0) -> bool:
    """Determine if filler should be used based on expected query time.
    
    Args:
        query_duration_estimate: Estimated query duration in seconds
        
    Returns:
        True if filler should be used
    """
    # Use filler if query is expected to take > 0.5 seconds
    return query_duration_estimate > 0.5

