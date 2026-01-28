"""Intent detection for past conversation references."""

import sys
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PastReferenceIntent:
    """Intent detected from user message about past conversations."""
    
    has_intent: bool
    intent_type: Optional[str] = None  # 'general', 'date', 'topic', 'progress', 'specific'
    date_range: Optional[Dict[str, datetime]] = None  # {'start': datetime, 'end': datetime}
    topics: Optional[List[str]] = None
    query_text: Optional[str] = None
    confidence: float = 0.0  # 0.0 to 1.0


def detect_past_reference_intent(user_message: str) -> PastReferenceIntent:
    """Detect if user message references past conversations.
    
    Args:
        user_message: User's message text
        
    Returns:
        PastReferenceIntent object with detection results
    """
    if not user_message or not user_message.strip():
        return PastReferenceIntent(has_intent=False)
    
    message_lower = user_message.lower().strip()
    
    # Keywords that indicate past reference
    past_keywords = [
        'what did we', 'what did i', 'what was', 'what were',
        'tell me about', 'remind me', 'remember when',
        'last time', 'before', 'previous', 'earlier', 'past',
        'ago', 'yesterday', 'last week', 'last month',
        'did we discuss', 'did we talk', 'did i mention',
        'what progress', 'how am i doing', 'my goal',
        'on [date]', 'in [month]', 'during',
        'past sessions', 'past conversations', 'what we discussed',
        'what we have discussed', 'what we talked about'
    ]
    
    # Check for past reference keywords
    has_past_keyword = any(keyword in message_lower for keyword in past_keywords)
    
    # Also check for variations like "what we have discussed", "what we've discussed"
    if not has_past_keyword:
        # Check for variations with "have" or "'ve"
        variations = [
            'what we have', 'what we\'ve', 'what we had',
            'discussed in the past', 'talked about before',
            'past session', 'previous session'
        ]
        has_past_keyword = any(variation in message_lower for variation in variations)
    
    if not has_past_keyword:
        return PastReferenceIntent(has_intent=False)
    
    # Detect intent type
    intent_type = None
    confidence = 0.5  # Base confidence
    
    # Date-specific queries
    date_patterns = [
        r'\b(yesterday|today|last week|last month|last year)\b',
        r'\b(on|in)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+\s+\d{1,2})\b',
        r'\b(\d+)\s+(days?|weeks?|months?)\s+ago\b'
    ]
    
    date_match = False
    for pattern in date_patterns:
        if re.search(pattern, message_lower):
            date_match = True
            intent_type = 'date'
            confidence = 0.8
            break
    
    # Topic-specific queries
    topic_keywords = ['about', 'regarding', 'concerning', 'related to']
    topic_match = any(keyword in message_lower for keyword in topic_keywords)
    
    if topic_match and not date_match:
        intent_type = 'topic'
        confidence = 0.7
    elif 'progress' in message_lower or 'goal' in message_lower:
        intent_type = 'progress'
        confidence = 0.75
    elif 'last time' in message_lower or 'before' in message_lower:
        intent_type = 'general'
        confidence = 0.8
    elif not intent_type:
        intent_type = 'general'
        confidence = 0.6
    
    # Extract topics
    topics = _extract_topics(message_lower)
    
    # Extract date range
    date_range = _extract_date_range(message_lower)
    
    return PastReferenceIntent(
        has_intent=True,
        intent_type=intent_type,
        date_range=date_range,
        topics=topics,
        query_text=user_message.strip(),
        confidence=confidence
    )


def _extract_topics(message: str) -> List[str]:
    """Extract topic keywords from message.
    
    Args:
        message: User message in lowercase
        
    Returns:
        List of topic keywords
    """
    # Common wellness topics
    wellness_topics = [
        'sleep', 'nutrition', 'diet', 'exercise', 'workout', 'fitness',
        'stress', 'anxiety', 'mental health', 'meditation', 'mindfulness',
        'weight', 'health', 'wellness', 'habits', 'routine', 'schedule',
        'energy', 'mood', 'pain', 'injury', 'recovery'
    ]
    
    found_topics = []
    for topic in wellness_topics:
        if topic in message:
            found_topics.append(topic)
    
    # Try to extract topic after "about" or "regarding"
    about_pattern = r'(?:about|regarding|concerning|related to)\s+([a-z\s]+?)(?:\?|\.|$)'
    match = re.search(about_pattern, message)
    if match:
        topic_text = match.group(1).strip()
        # Extract key words from topic text
        words = topic_text.split()
        found_topics.extend([w for w in words if len(w) > 3])
    
    return list(set(found_topics))  # Remove duplicates


def _extract_date_range(message: str) -> Optional[Dict[str, datetime]]:
    """Extract date range from message.
    
    Args:
        message: User message in lowercase
        
    Returns:
        Dict with 'start' and 'end' datetime or None
    """
    now = datetime.now()
    
    # Simple date extraction
    if 'yesterday' in message:
        yesterday = now - timedelta(days=1)
        return {
            'start': yesterday.replace(hour=0, minute=0, second=0),
            'end': yesterday.replace(hour=23, minute=59, second=59)
        }
    
    if 'last week' in message:
        last_week_start = now - timedelta(days=now.weekday() + 7)
        last_week_end = last_week_start + timedelta(days=6)
        return {
            'start': last_week_start.replace(hour=0, minute=0, second=0),
            'end': last_week_end.replace(hour=23, minute=59, second=59)
        }
    
    if 'last month' in message:
        first_day_this_month = now.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        return {
            'start': first_day_last_month.replace(hour=0, minute=0, second=0),
            'end': last_day_last_month.replace(hour=23, minute=59, second=59)
        }
    
    # Extract "X days ago" pattern
    days_ago_pattern = r'(\d+)\s+days?\s+ago'
    match = re.search(days_ago_pattern, message)
    if match:
        days = int(match.group(1))
        target_date = now - timedelta(days=days)
        return {
            'start': target_date.replace(hour=0, minute=0, second=0),
            'end': target_date.replace(hour=23, minute=59, second=59)
        }
    
    return None

