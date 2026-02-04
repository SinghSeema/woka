"""Intent detection for past conversation references."""

import sys
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.topic_extractor import extract_topics_from_query

logger = get_logger(__name__)

# Cached reference pattern embedding (generated once, lazy-loaded)
_past_reference_pattern = "what did we discuss or talk about in past conversations or previous sessions"
_pattern_embedding = None


@dataclass
class PastReferenceIntent:
    """Intent detected from user message about past conversations."""
    
    has_intent: bool
    intent_type: Optional[str] = None  # 'general', 'date', 'topic', 'progress', 'specific'
    date_range: Optional[Dict[str, datetime]] = None  # {'start': datetime, 'end': datetime}
    topics: Optional[List[str]] = None
    query_text: Optional[str] = None
    confidence: float = 0.0  # 0.0 to 1.0


async def detect_past_reference_intent(user_message: str) -> PastReferenceIntent:
    """Detect if user message references past conversations.
    
    Uses hybrid approach: regex fast path for common patterns, 
    local embeddings for edge cases and paraphrases.
    
    Args:
        user_message: User's message text
        
    Returns:
        PastReferenceIntent object with detection results
    """
    if not user_message or not user_message.strip():
        return PastReferenceIntent(has_intent=False)
    
    # Fast path: Regex for high-confidence patterns (<1ms for 95% of queries)
    regex_result = _detect_with_regex(user_message)
    if regex_result.confidence >= 0.85:
        logger.debug(f"Intent detected via regex fast path: {regex_result.intent_type} (confidence: {regex_result.confidence:.2f})")
        return regex_result
    
    # Semantic path: Local embeddings for edge cases (5-10ms for 5% of queries)
    if settings.ENABLE_SEMANTIC_SEARCH:
        try:
            embedding_result = await _detect_with_embeddings(user_message)
            if embedding_result and embedding_result.confidence > regex_result.confidence:
                logger.debug(f"Intent detected via embeddings: {embedding_result.intent_type} (confidence: {embedding_result.confidence:.2f})")
                return embedding_result
        except Exception as e:
            logger.warning(f"Embedding-based intent detection failed, falling back to regex: {e}")
    
    # Fallback to regex result
    logger.debug(f"Intent detected via regex fallback: {regex_result.intent_type} (confidence: {regex_result.confidence:.2f})")
    return regex_result


def _detect_with_regex(user_message: str) -> PastReferenceIntent:
    """Fast regex-based intent detection for common patterns.
    
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
    
    # Extract topics using shared topic extractor
    topics = extract_topics_from_query(user_message)
    
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


async def _detect_with_embeddings(query: str) -> Optional[PastReferenceIntent]:
    """Use local embedding model to detect past reference intent.
    
    Uses cosine similarity against a reference pattern embedding.
    Reuses existing embedding_service.py infrastructure.
    
    Args:
        query: User's message text
        
    Returns:
        PastReferenceIntent if detected, None otherwise
    """
    try:
        from bot.services.embedding_service import generate_embedding
        
        # Get reference pattern embedding (cached, generated once)
        pattern_embedding = await _get_past_reference_pattern_embedding()
        if not pattern_embedding:
            logger.debug("Reference pattern embedding not available")
            return None
        
        # Generate query embedding using existing service
        query_embedding = await generate_embedding(query)
        if not query_embedding:
            logger.debug("Failed to generate query embedding")
            return None
        
        # Calculate cosine similarity
        similarity = _cosine_similarity(query_embedding, pattern_embedding)
        
        # Threshold for past reference detection
        threshold = getattr(settings, 'INTENT_DETECTION_THRESHOLD', 0.65)
        
        if similarity >= threshold:
            # Extract metadata using regex (single source of truth)
            regex_result = _detect_with_regex(query)
            if regex_result.has_intent:
                # Use embedding similarity as confidence, but regex metadata
                return PastReferenceIntent(
                    has_intent=True,
                    intent_type=regex_result.intent_type,
                    date_range=regex_result.date_range,
                    topics=regex_result.topics,
                    query_text=query.strip(),
                    confidence=similarity  # Use similarity as confidence
                )
            else:
                # Even if regex doesn't match, if embedding similarity is high,
                # it's likely a past reference query (paraphrase)
                # Extract basic metadata
                topics = extract_topics_from_query(query)
                date_range = _extract_date_range(query.lower())
                
                # Determine intent type from metadata
                intent_type = 'general'
                if date_range:
                    intent_type = 'date'
                elif topics:
                    intent_type = 'topic'
                
                return PastReferenceIntent(
                    has_intent=True,
                    intent_type=intent_type,
                    date_range=date_range,
                    topics=topics,
                    query_text=query.strip(),
                    confidence=similarity
                )
        
        return None
    except Exception as e:
        logger.error(f"Error in embedding-based intent detection: {e}", exc_info=True)
        return None


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
        
    Returns:
        Cosine similarity score (0.0 to 1.0)
    """
    try:
        # Use NumPy if available (faster)
        if HAS_NUMPY and np:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(dot_product / (norm1 * norm2))
    except Exception:
        pass
    
    # Fallback: Manual calculation
    if len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


async def _get_past_reference_pattern_embedding() -> Optional[List[float]]:
    """Get or generate the reference pattern embedding (cached).
    
    Returns:
        Reference pattern embedding vector or None
    """
    global _pattern_embedding
    if _pattern_embedding is None:
        try:
            from bot.services.embedding_service import generate_embedding
            _pattern_embedding = await generate_embedding(_past_reference_pattern)
            if _pattern_embedding:
                logger.debug(f"Generated reference pattern embedding (dim: {len(_pattern_embedding)})")
            else:
                logger.warning("Failed to generate reference pattern embedding")
        except Exception as e:
            logger.error(f"Error generating reference pattern embedding: {e}", exc_info=True)
    return _pattern_embedding


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

