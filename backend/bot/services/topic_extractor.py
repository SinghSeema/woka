"""Topic extraction service for wellness conversations.

Current Approach: Keyword-based extraction using vocabulary matching.
- Fast, predictable, no API costs
- Requires manual vocabulary updates for new topics
- See docs/TOPIC_EXTRACTION_STRATEGY.md for details

Future Approach: Fine-tuned SBERT model (planned)
- Automatic topic understanding, handles synonyms
- See docs/FINETUNING_SBERT_FOR_WELLNESS.md for implementation plan
"""

import sys
from pathlib import Path
from typing import List, Set
import re

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Wellness topics vocabulary
WELLNESS_TOPICS = {
    # Sleep & Rest
    'sleep', 'rest', 'insomnia', 'sleeping', 'bedtime', 'wake', 'tired', 'fatigue',
    'sleep schedule', 'sleep quality', 'sleep pattern',
    
    # Nutrition & Diet
    'nutrition', 'diet', 'food', 'eating', 'meal', 'calorie', 'protein', 'carb',
    'vegetable', 'fruit', 'healthy eating', 'meal prep', 'cooking', 'breakfast',
    'lunch', 'dinner', 'snack', 'hydration', 'water',
    
    # Exercise & Fitness
    'exercise', 'workout', 'fitness', 'training', 'gym', 'running', 'walking',
    'cardio', 'strength', 'yoga', 'stretching', 'movement', 'activity', 'sport',
    'jogging', 'cycling', 'swimming', 'zumba', 'dancing', 'dance', 'aerobics',
    'pilates', 'crossfit', 'weightlifting', 'lifting', 'singing', 'music', 'vocal',
    
    # Mental Health
    'stress', 'anxiety', 'mental health', 'depression', 'mood', 'emotion',
    'meditation', 'mindfulness', 'breathing', 'relaxation', 'calm', 'peace',
    'mental wellness', 'emotional health',
    
    # Physical Health
    'pain', 'injury', 'recovery', 'illness', 'symptoms', 'health', 'wellness',
    'energy', 'weight', 'body', 'knee', 'back', 'shoulder', 'joint', 'muscle',
    'ache', 'discomfort', 'healing',
    
    # Habits & Routine
    'habit', 'routine', 'schedule', 'consistency', 'discipline', 'motivation',
    'goal', 'progress', 'achievement', 'challenge', 'struggle', 'commitment',
    'lifestyle', 'pattern',
    
    # Hobbies & Leisure Activities
    'reading', 'books', 'book', 'hobby', 'hobbies', 'leisure', 'recreation',
    'writing', 'journaling', 'drawing', 'painting', 'art', 'crafts', 'knitting',
    'photography', 'gardening', 'cooking', 'baking', 'travel', 'traveling',
    'learning', 'education', 'study', 'studying', 'course', 'class', 'classes',
    
    # Medical
    'doctor', 'treatment', 'medicine', 'medication', 'therapy', 'appointment',
    'diagnosis', 'condition', 'chronic', 'medical', 'healthcare',
}

# Stop words to filter out
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
    'we', 'did', 'do', 'what', 'when', 'where', 'how', 'why', 'about', 'regarding', 'concerning',
    'related', 'discuss', 'discussed', 'talk', 'talked', 'mention', 'mentioned', 'say', 'said',
    'this', 'that', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must',
    'just', 'only', 'also', 'too', 'very', 'much', 'more', 'most', 'some', 'any',
    'past', 'previous', 'before', 'ago', 'last', 'time', 'times', 'session', 'conversation',
    'user', 'coach', 'assistant', 'they', 'them', 'their', 'you', 'your', 'yours'
}


def extract_topics(text: str, min_confidence: float = 0.5) -> List[str]:
    """Extract wellness topics from text.
    
    Args:
        text: Text to extract topics from (summary, query, etc.)
        min_confidence: Minimum confidence threshold (0.0-1.0) - currently unused but reserved for future
        
    Returns:
        List of unique topic keywords found in text, sorted alphabetically
    """
    if not text or not text.strip():
        return []
    
    text_lower = text.lower().strip()
    found_topics: Set[str] = set()
    
    # Method 1: Direct vocabulary matching (case-insensitive)
    for topic in WELLNESS_TOPICS:
        if topic in text_lower:
            found_topics.add(topic)
    
    # Method 2: Extract topics after "about", "regarding", etc.
    about_pattern = r'(?:about|regarding|concerning|related to|discuss|talked about|discussed|focus on|concerning|mention|mentioned)\s+([a-z\s]+?)(?:\?|\.|,|$|and|or)'
    matches = re.finditer(about_pattern, text_lower)
    for match in matches:
        topic_text = match.group(1).strip()
        words = [w for w in topic_text.split() if len(w) > 2]
        # Check if words match known topics
        for word in words:
            if word in WELLNESS_TOPICS:
                found_topics.add(word)
        # Also check for multi-word topics
        for topic in WELLNESS_TOPICS:
            if ' ' in topic and topic in topic_text:
                found_topics.add(topic)
    
    # Method 3: Extract from common patterns
    discuss_pattern = r'(?:discuss|talk|mention|say|cover|address|focus|concentrate)\s+(?:on\s+|about\s+)?([a-z\s]+?)(?:\?|\.|,|$|and|or)'
    matches = re.finditer(discuss_pattern, text_lower)
    for match in matches:
        topic_text = match.group(1).strip()
        words = [w for w in topic_text.split() if len(w) > 2]
        for word in words:
            if word in WELLNESS_TOPICS:
                found_topics.add(word)
        # Check for multi-word topics
        for topic in WELLNESS_TOPICS:
            if ' ' in topic and topic in topic_text:
                found_topics.add(topic)
    
    # Method 4: Look for topic keywords in context (e.g., "sleep schedule", "knee pain")
    for topic in WELLNESS_TOPICS:
        # Check if topic appears as a standalone word or in common phrases
        pattern = r'\b' + re.escape(topic) + r'\b'
        if re.search(pattern, text_lower):
            found_topics.add(topic)
    
    # Filter out stop words
    found_topics = {t for t in found_topics if t not in STOP_WORDS}
    
    # Remove duplicates and sort for consistency
    result = sorted(list(found_topics))
    return result


def extract_topics_from_user_messages(user_messages: List[str]) -> List[str]:
    """Extract topics from user messages only (not from assistant responses or summaries).
    
    This ensures topics reflect what the USER actually asked about, not what the assistant
    discussed in response. More strict extraction - only extracts topics explicitly mentioned
    by the user.
    
    Args:
        user_messages: List of user message strings from the transcript
        
    Returns:
        List of unique topics mentioned by the user
    """
    if not user_messages:
        return []
    
    # Combine all user messages
    all_user_text = " ".join(user_messages)
    
    # Use strict extraction - only extract topics explicitly mentioned
    # Don't extract generic terms unless they're clearly the focus
    found_topics: Set[str] = set()
    text_lower = all_user_text.lower()
    
    # Method 1: Direct vocabulary matching - only if topic appears as a word boundary
    # This prevents matching "exercise" in "exercised" or partial matches
    for topic in WELLNESS_TOPICS:
        # Use word boundary to match whole words only
        pattern = r'\b' + re.escape(topic) + r'\b'
        if re.search(pattern, text_lower):
            found_topics.add(topic)
    
    # Method 2: Extract topics after explicit question patterns
    # Only extract if user explicitly asks "about X" or "regarding X"
    about_pattern = r'(?:about|regarding|concerning|related to|discuss|talk about|mention|ask about)\s+([a-z\s]+?)(?:\?|\.|,|$|and|or)'
    matches = re.finditer(about_pattern, text_lower)
    for match in matches:
        topic_text = match.group(1).strip()
        # Extract individual words that match known topics
        words = topic_text.split()
        for word in words:
            if word in WELLNESS_TOPICS and len(word) > 2:
                found_topics.add(word)
        # Check for multi-word topics
        for topic in WELLNESS_TOPICS:
            if ' ' in topic and topic in topic_text:
                found_topics.add(topic)
    
    # Method 3: Extract from "I want to [topic]" or "I need help with [topic]" patterns
    want_pattern = r'(?:want to|need help with|interested in|focus on|working on|struggling with|having trouble with)\s+([a-z\s]+?)(?:\?|\.|,|$|and|or)'
    matches = re.finditer(want_pattern, text_lower)
    for match in matches:
        topic_text = match.group(1).strip()
        words = topic_text.split()
        for word in words:
            if word in WELLNESS_TOPICS and len(word) > 2:
                found_topics.add(word)
        for topic in WELLNESS_TOPICS:
            if ' ' in topic and topic in topic_text:
                found_topics.add(topic)
    
    # Filter out stop words
    found_topics = {t for t in found_topics if t not in STOP_WORDS}
    
    # Additional filtering: Remove very generic topics unless explicitly mentioned
    # Generic topics that are too broad and shouldn't be extracted unless user specifically asks
    generic_topics = {
        'health', 'wellness', 'goal', 'progress', 'routine', 'schedule', 
        'habit', 'lifestyle', 'fitness', 'exercise', 'workout', 'activity',
        'movement', 'nutrition', 'diet', 'food', 'eating'
    }
    
    # If we have specific topics, remove generic ones unless they were explicitly mentioned
    specific_topics = found_topics - generic_topics
    if specific_topics:
        # Keep only generic topics that were explicitly mentioned in question patterns
        explicit_generic = set()
        for topic in generic_topics:
            if topic in found_topics:
                # Check if it was mentioned in an explicit pattern (user asked about it)
                explicit_patterns = [
                    rf'\b(?:about|regarding|concerning|related to|discuss|talk about|mention|ask about)\s+{re.escape(topic)}\b',
                    rf'\b(?:want to|need help with|interested in|focus on|working on|struggling with)\s+{re.escape(topic)}\b',
                    rf'\b{re.escape(topic)}\s+(?:goal|plan|routine|schedule|progress)',  # "exercise goal", "diet plan"
                ]
                for pattern in explicit_patterns:
                    if re.search(pattern, text_lower):
                        explicit_generic.add(topic)
                        break
        found_topics = specific_topics | explicit_generic
    # If no specific topics, keep generic ones only if explicitly mentioned
    elif found_topics:
        # Filter to only keep generic topics that were explicitly mentioned
        explicit_generic = set()
        for topic in found_topics:
            if topic in generic_topics:
                explicit_patterns = [
                    rf'\b(?:about|regarding|concerning|related to|discuss|talk about|mention|ask about)\s+{re.escape(topic)}\b',
                    rf'\b(?:want to|need help with|interested in|focus on|working on|struggling with)\s+{re.escape(topic)}\b',
                ]
                for pattern in explicit_patterns:
                    if re.search(pattern, text_lower):
                        explicit_generic.add(topic)
                        break
        found_topics = explicit_generic
    
    result = sorted(list(found_topics))
    
    return result


def extract_topics_from_query(query: str) -> List[str]:
    """Extract topics from user query.
    
    Optimized for short query text. Uses strict extraction - only extracts topics
    explicitly mentioned in the query.
    
    Args:
        query: User query text
        
    Returns:
        List of topics
    """
    # Treat single query as a list of user messages
    return extract_topics_from_user_messages([query])


async def extract_topics_from_user_messages_hybrid(user_messages: List[str]) -> List[str]:
    """Extract topics from user messages using hybrid approach.
    
    Primary: Keyword-based extraction (fast, no API costs)
    Secondary: LLM-based few-shot extraction (when enabled) to catch topics not in vocabulary
    
    This function combines both approaches to ensure we capture:
    - Known topics from keyword extraction (fast)
    - New/unknown topics from LLM extraction (e.g., "jumping", "knitting")
    
    This function is async and should be used in async contexts (e.g., session summary generation).
    For synchronous contexts, use extract_topics_from_user_messages().
    
    Args:
        user_messages: List of user message strings from the transcript
        
    Returns:
        List of unique topics mentioned by the user (merged from both keyword and LLM extraction)
    """
    if not user_messages:
        return []
    
    # Step 1: Try keyword-based extraction first (fast path)
    keyword_topics = extract_topics_from_user_messages(user_messages)
    
    # Step 2: If LLM fallback is enabled, also try LLM extraction to catch new topics
    # This runs in addition to keyword extraction, not just as a fallback
    all_topics = set(keyword_topics)  # Start with keyword topics
    
    if getattr(settings, 'ENABLE_LLM_TOPIC_FALLBACK', False):
        try:
            from bot.services.llm_topic_extractor import extract_topics_fewshot
            
            # Combine user messages for LLM extraction
            combined_text = " ".join(user_messages)
            llm_topics = await extract_topics_fewshot(combined_text)
            
            # Merge LLM topics with keyword topics (deduplicated)
            if llm_topics:
                all_topics.update(llm_topics)
                logger.info(
                    f"✅ [HYBRID TOPICS] keyword={len(keyword_topics)}, LLM={len(llm_topics)}, "
                    f"merged={len(all_topics)} unique: {sorted(list(all_topics))}"
                )
        except Exception as e:
            logger.warning(
                f"⚠️  [HYBRID TOPICS] LLM extraction failed: {type(e).__name__}: {e}, "
                f"using keyword topics only: {keyword_topics}"
            )
            # Continue with keyword topics only if LLM fails
    
    # Step 3: Return merged and deduplicated topics
    result = sorted(list(all_topics))
    return result

