"""LLM-based topic extraction using few-shot learning as fallback.

This module provides a Groq LLM-based topic extraction fallback that triggers
only when keyword-based extraction returns no topics. Uses strict JSON parsing
and canonicalization to ensure safe, high-quality topic extraction.
"""

import sys
import json
import re
from pathlib import Path
from typing import List, Optional, Set
from functools import lru_cache
import hashlib
import httpx

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Lazy import to avoid circular dependencies and slow startup
_WELLNESS_TOPICS = None
_STOP_WORDS = None


def _get_wellness_topics():
    """Lazy import of wellness topics to avoid blocking agent initialization."""
    global _WELLNESS_TOPICS, _STOP_WORDS
    if _WELLNESS_TOPICS is None:
        from bot.services.topic_extractor import WELLNESS_TOPICS, STOP_WORDS
        _WELLNESS_TOPICS = WELLNESS_TOPICS
        _STOP_WORDS = STOP_WORDS
    return _WELLNESS_TOPICS, _STOP_WORDS

# In-memory cache for topic extraction results (keyed by normalized text hash)
_topic_cache: dict[str, List[str]] = {}
_cache_max_size = 100  # Limit cache size


def _normalize_text(text: str) -> str:
    """Normalize text for caching (lowercase, strip, remove extra spaces)."""
    return " ".join(text.lower().strip().split())


def _get_cache_key(text: str) -> str:
    """Generate cache key from normalized text."""
    normalized = _normalize_text(text)
    return hashlib.md5(normalized.encode()).hexdigest()


def _canonicalize_topic(topic: str, user_text: str) -> Optional[str]:
    """Canonicalize a topic extracted by LLM.
    
    Maps LLM-proposed topics to canonical vocabulary:
    1. Exact match against WELLNESS_TOPICS
    2. Light stemming/singularization (e.g., "books" -> "book")
    3. Keep unknown topics only if they appear verbatim in user text
    
    Args:
        topic: Topic string from LLM
        user_text: Original user text (for verification)
        
    Returns:
        Canonicalized topic string or None if should be filtered out
    """
    if not topic or not topic.strip():
        return None
    
    topic_lower = topic.lower().strip()
    user_text_lower = user_text.lower()
    
    # Lazy import to avoid blocking initialization
    WELLNESS_TOPICS, STOP_WORDS = _get_wellness_topics()
    
    # Filter out stop words
    if topic_lower in STOP_WORDS:
        return None
    
    # Filter out very short or very long topics
    if len(topic_lower) < 2 or len(topic_lower) > 32:
        return None
    
    # Step 1: Exact match against WELLNESS_TOPICS
    if topic_lower in WELLNESS_TOPICS:
        return topic_lower
    
    # Step 2: Try singularization/stemming for common patterns
    # Remove trailing 's' for plurals
    if topic_lower.endswith('s') and len(topic_lower) > 3:
        singular = topic_lower[:-1]
        if singular in WELLNESS_TOPICS:
            return singular
    
    # Step 3: Check if topic appears verbatim in user text (prevents hallucinations)
    # Use word boundary to match whole words
    pattern = r'\b' + re.escape(topic_lower) + r'\b'
    if re.search(pattern, user_text_lower):
        # Topic appears in user text - keep it even if not in vocabulary
        # This allows new topics like "reading", "knitting", etc.
        return topic_lower
    
    # Topic not in vocabulary and not in user text - likely hallucination
    return None


def _post_process_topics(topics: List[str], user_text: str, max_topics: int = 5) -> List[str]:
    """Post-process LLM-extracted topics with safety constraints.
    
    Args:
        topics: Raw topics from LLM
        user_text: Original user text
        max_topics: Maximum number of topics to return
        
    Returns:
        Cleaned, canonicalized list of topics
    """
    if not topics:
        return []
    
    # Step 1: Basic cleaning (lowercase, trim, dedupe)
    cleaned = []
    seen = set()
    for topic in topics:
        if not isinstance(topic, str):
            continue
        topic_clean = topic.lower().strip()
        if topic_clean and topic_clean not in seen:
            seen.add(topic_clean)
            cleaned.append(topic_clean)
    
    # Step 2: Canonicalize each topic
    canonicalized = []
    for topic in cleaned:
        canonical = _canonicalize_topic(topic, user_text)
        if canonical:
            canonicalized.append(canonical)
    
    # Step 3: Limit to max_topics
    result = canonicalized[:max_topics]
    
    # Step 4: Remove duplicates again (canonicalization might create duplicates)
    result = sorted(list(set(result)))
    
    return result


async def extract_topics_fewshot(user_text: str) -> List[str]:
    """Extract topics using Groq LLM with few-shot learning.
    
    This is a fallback that triggers only when keyword-based extraction
    returns no topics. Uses strict JSON parsing and post-processing to
    ensure safe, high-quality topic extraction.
    
    Args:
        user_text: User message text to extract topics from
        
    Returns:
        List of extracted topics (canonicalized and validated)
    """
    if not user_text or not user_text.strip():
        return []
    
    # Check cache first
    cache_key = _get_cache_key(user_text)
    if cache_key in _topic_cache:
        return _topic_cache[cache_key]
    
    # Check if Groq is configured
    if not getattr(settings, 'GROQ_API_KEY', None):
        return []
    
    if not getattr(settings, 'LLM_MODEL', None):
        return []
    
    try:
        # Few-shot prompt with examples
        prompt = f"""Extract wellness topics from this user message. Return ONLY a JSON array of topic strings, nothing else.

Examples:
- "I want to start reading books" → ["reading", "books", "hobby"]
- "Let's talk about zumba classes" → ["zumba", "exercise", "fitness"]
- "I'm interested in meditation" → ["meditation", "mindfulness"]
- "Today, let's talk about new hobby as reading" → ["reading", "hobby"]
- "I need help with sleep schedule" → ["sleep", "schedule"]

User message: "{user_text}"

Return only a JSON array, e.g. ["topic1", "topic2"]:"""

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.LLM_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a topic extraction assistant. Extract wellness-related topics from user messages. Return ONLY a JSON array of topic strings. Do not include any explanation or other text."
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,  # Low temperature for consistency
                    "max_tokens": 100,  # Small response (just JSON array)
                },
            )
            response.raise_for_status()
            result = response.json()
            llm_output = result["choices"][0]["message"]["content"].strip()
            
            # Parse JSON from response (handle cases where LLM adds extra text)
            topics = _parse_json_topics(llm_output)
            
            # Post-process topics
            processed_topics = _post_process_topics(topics, user_text, max_topics=5)
            
            # Cache result (with size limit)
            if len(_topic_cache) >= _cache_max_size:
                # Remove oldest entry (FIFO - dict maintains insertion order in Python 3.7+)
                oldest_key = next(iter(_topic_cache))
                del _topic_cache[oldest_key]
            _topic_cache[cache_key] = processed_topics
            
            if processed_topics:
                logger.info(
                    f"✅ [LLM TOPICS] Extracted {len(processed_topics)} topics: {processed_topics} "
                    f"(query: '{user_text[:50]}...')"
                )
            
            return processed_topics
            
    except json.JSONDecodeError as e:
        logger.warning(
            f"⚠️  [LLM TOPICS] JSON parse failed | Error: {e} | "
            f"Response: {llm_output[:150] if 'llm_output' in locals() else 'N/A'}"
        )
        return []
    except httpx.HTTPStatusError as e:
        logger.error(
            f"❌ [LLM TOPICS] HTTP error {e.response.status_code} | "
            f"Response: {e.response.text[:200] if hasattr(e.response, 'text') else 'N/A'}"
        )
        return []
    except httpx.TimeoutException:
        logger.warning("⚠️  [LLM TOPICS] Request timeout (10s), skipping LLM extraction")
        return []
    except Exception as e:
        logger.error(f"❌ [LLM TOPICS] Unexpected error: {type(e).__name__}: {e}", exc_info=True)
        return []


def _parse_json_topics(text: str) -> List[str]:
    """Parse JSON array of topics from LLM response.
    
    Handles cases where LLM adds extra text before/after JSON.
    
    Args:
        text: LLM response text
        
    Returns:
        List of topic strings
    """
    if not text:
        return []
    
    # Try to find JSON array in the response
    # Look for pattern: [...] or ["topic1", "topic2"]
    json_pattern = r'\[.*?\]'
    matches = re.findall(json_pattern, text, re.DOTALL)
    
    if matches:
        # Try to parse the first match
        for match in matches:
            try:
                topics = json.loads(match)
                if isinstance(topics, list):
                    return [str(t) for t in topics if t]
            except json.JSONDecodeError:
                continue
    
    # Fallback: try parsing the entire text as JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(t) for t in parsed if t]
    except json.JSONDecodeError:
        pass
    
    # If all parsing fails, return empty list
    return []


async def consolidate_topics(topics: List[str], max_topics: int = 5) -> List[str]:
    """Consolidate related topics into high-level categories using LLM.
    
    This function is used when storing sessions to keep topic lists clean and manageable.
    For example: ["drawing", "sketching", "painting", "watercolor"] → ["art"]
    
    Args:
        topics: List of extracted topics (can be many)
        max_topics: Maximum number of consolidated topics to return (default: 5)
        
    Returns:
        List of consolidated topics (3-5 high-level topics)
    """
    if not topics or len(topics) <= max_topics:
        # Already within limit, return as-is
        return topics[:max_topics] if topics else []
    
    # Check if Groq is configured
    if not getattr(settings, 'GROQ_API_KEY', None) or not getattr(settings, 'LLM_MODEL', None):
        return topics[:max_topics]
    
    try:
        # Consolidation prompt
        topics_str = ", ".join(topics)
        prompt = f"""Consolidate these wellness topics into 3-5 high-level categories. Group related topics together.

Examples:
- ["drawing", "sketching", "painting", "watercolor"] → ["art"]
- ["running", "jogging", "cardio"] → ["exercise", "cardio"]
- ["sleep", "bedtime", "rest"] → ["sleep"]
- ["reading", "books", "literature"] → ["reading", "hobby"]
- ["zumba", "dancing", "aerobics"] → ["exercise", "dancing"]

Topics to consolidate: [{topics_str}]

Return ONLY a JSON array of 3-5 consolidated topics, e.g. ["topic1", "topic2"]:"""

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.LLM_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a topic consolidation assistant. Consolidate related wellness topics into high-level categories. Return ONLY a JSON array of 3-5 topic strings. Do not include any explanation."
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 100,
                },
            )
            response.raise_for_status()
            result = response.json()
            llm_output = result["choices"][0]["message"]["content"].strip()
            
            # Parse JSON
            consolidated = _parse_json_topics(llm_output)
            
            # Post-process: ensure we have valid topics
            if consolidated:
                # Limit to max_topics
                consolidated = consolidated[:max_topics]
                logger.info(
                    f"✅ [TOPIC CONSOLIDATION] {len(topics)} → {len(consolidated)} topics: {consolidated}"
                )
                return consolidated
            else:
                logger.warning(
                    f"⚠️  [TOPIC CONSOLIDATION] LLM returned empty, using top {max_topics} topics: {topics[:max_topics]}"
                )
                return topics[:max_topics]
                
    except httpx.HTTPStatusError as e:
        logger.error(
            f"❌ [TOPIC CONSOLIDATION] HTTP error {e.response.status_code}, using top {max_topics} topics"
        )
        return topics[:max_topics]
    except httpx.TimeoutException:
        logger.warning(f"⚠️  [TOPIC CONSOLIDATION] Timeout, using top {max_topics} topics")
        return topics[:max_topics]
    except Exception as e:
        logger.error(
            f"❌ [TOPIC CONSOLIDATION] Error: {type(e).__name__}: {e}, using top {max_topics} topics",
            exc_info=True
        )
        return topics[:max_topics]


async def match_topics_semantically(
    query_topics: List[str],
    stored_topics: List[str],
    similarity_threshold: float = 0.7
) -> List[str]:
    """Match query topics to stored topics using semantic similarity.
    
    This handles cases where query uses synonyms (e.g., "drawing") but
    stored topic is consolidated (e.g., "art").
    
    Args:
        query_topics: Topics extracted from user query (e.g., ["drawing"])
        stored_topics: Topics stored in database (e.g., ["art", "hobby"])
        similarity_threshold: Minimum similarity to consider a match (default: 0.7)
        
    Returns:
        List of stored topics that semantically match query topics
    """
    if not query_topics or not stored_topics:
        return []
    
    try:
        from bot.services.embedding_service import generate_embedding
        import numpy as np
        
        # Generate embeddings for query topics
        query_embeddings = {}
        for topic in query_topics:
            embedding = await generate_embedding(topic)
            if embedding:
                query_embeddings[topic] = embedding
        
        if not query_embeddings:
            # Fallback to exact match
            return [t for t in stored_topics if t.lower() in [q.lower() for q in query_topics]]
        
        # Generate embeddings for stored topics
        stored_embeddings = {}
        for topic in stored_topics:
            embedding = await generate_embedding(topic)
            if embedding:
                stored_embeddings[topic] = embedding
        
        if not stored_embeddings:
            return [t for t in stored_topics if t.lower() in [q.lower() for q in query_topics]]
        
        # Calculate cosine similarity between query and stored topics
        matched_topics = []
        for query_topic, query_emb in query_embeddings.items():
            best_match = None
            best_similarity = 0.0
            
            for stored_topic, stored_emb in stored_embeddings.items():
                # Cosine similarity
                similarity = np.dot(query_emb, stored_emb) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(stored_emb)
                )
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = stored_topic
            
            # If similarity is above threshold, add to matched topics
            if best_match and best_similarity >= similarity_threshold:
                if best_match not in matched_topics:
                    matched_topics.append(best_match)
                    logger.info(
                        f"✅ [SEMANTIC MATCH] '{query_topic}' → '{best_match}' "
                        f"(similarity: {best_similarity:.3f})"
                    )
        
        # Also check for exact matches (case-insensitive)
        for query_topic in query_topics:
            for stored_topic in stored_topics:
                if query_topic.lower() == stored_topic.lower():
                    if stored_topic not in matched_topics:
                        matched_topics.append(stored_topic)
        
        return matched_topics
        
    except Exception as e:
        logger.error(
            f"❌ [SEMANTIC MATCH] Error: {type(e).__name__}: {e}, falling back to exact match",
            exc_info=True
        )
        # Fallback to exact match
        return [t for t in stored_topics if t.lower() in [q.lower() for q in query_topics]]

