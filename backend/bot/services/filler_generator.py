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
        "Give me a moment...",
        "Sure, one second...",
        "Let me think...",
        "Hmm, give me just a sec...",
        "Hold on a moment...",
    ],
    "date": [
        "Let me cast my mind back...",
        "Hmm, let me think about that time...",
        "Give me a moment, I'm going back through our sessions...",
        "One sec, let me think back...",
    ],
    "topic": [
        "Hmm, let me think if we talked about that...",
        "Give me a moment, I'm recalling our conversations...",
        "Let me think back on that...",
        "One second, casting my mind back...",
    ],
    "semantic": [
        "Hmm, let me think...",
        "Give me a moment, I'm recalling what we discussed...",
        "Let me cast my mind back...",
        "One sec, I'm thinking...",
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

