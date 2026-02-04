"""Query understanding and expansion for better semantic search."""

import sys
from pathlib import Path
from typing import Optional, Dict, Any
import re

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.logging import get_logger
from bot.services.intent_detector import PastReferenceIntent

logger = get_logger(__name__)


class QueryUnderstanding:
    """Query understanding and expansion for improved semantic search."""
    
    def __init__(self):
        """Initialize query understanding service."""
        pass
    
    def expand_query(self, query: str, intent: PastReferenceIntent) -> str:
        """Expand query for better semantic search.
        
        Adds context and synonyms to improve embedding quality.
        Especially useful for short queries like "singing" → "discussion about singing".
        
        For topic queries, extracts just the topic-related parts to improve matching.
        
        Args:
            query: Original user query
            intent: Detected intent with metadata
            
        Returns:
            Expanded query text
        """
        if not query or not query.strip():
            return query
        
        query_lower = query.lower().strip()
        expanded = query
        
        # For topic queries, extract and focus on the topic part
        if intent.intent_type == 'topic' and intent.topics:
            # Extract the core topic query - remove conversational fluff
            # e.g., "I'm doing good. In our past session, did we discuss about cardio?"
            # → "discussion about cardio"
            topics_str = " ".join(intent.topics)
            
            # Check if query is verbose (has conversational elements)
            verbose_indicators = ["i'm", "i am", "doing good", "doing well", "how are you", 
                                 "in our past", "in the past", "did we", "have we"]
            is_verbose = any(indicator in query_lower for indicator in verbose_indicators)
            
            if is_verbose:
                # For verbose queries, extract just the topic-focused part
                expanded = f"discussion about {topics_str}"
                logger.debug(f"Extracted topic from verbose query: '{query[:60]}...' → '{expanded}'")
            else:
                # For short queries, add context
                words = query_lower.split()
                if len(words) < 3:
                    expanded = f"discussion about {topics_str}"
                    logger.debug(f"Expanded short topic query: '{query}' → '{expanded}'")
        # For very short queries (< 3 words), add context
        else:
            words = query_lower.split()
            if len(words) < 3:
                # If it's a general past reference, add context
                if intent.intent_type == 'general':
                    expanded = f"what did we discuss about {query}"
                    logger.debug(f"Expanded short general query: '{query}' → '{expanded}'")
        
        # Add synonyms for common wellness terms
        expanded = self._add_synonyms(expanded)
        
        return expanded
    
    def _add_synonyms(self, query: str) -> str:
        """Add synonyms for common wellness terms.
        
        Args:
            query: Query text
            
        Returns:
            Query with synonyms added
        """
        # Common synonym mappings
        synonyms = {
            r'\bsleep\b': 'sleep rest bedtime',
            r'\bexercise\b': 'exercise workout fitness',
            r'\bdiet\b': 'diet nutrition food eating',
            r'\bweight\b': 'weight weight loss weight management',
            r'\bgoal\b': 'goal objective target',
            r'\bprogress\b': 'progress improvement advancement',
        }
        
        expanded = query
        for pattern, replacement in synonyms.items():
            if re.search(pattern, query.lower()):
                # Add synonyms after the matched term
                expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
                logger.debug(f"Added synonyms: '{query}' → '{expanded}'")
                break  # Only apply first match
        
        return expanded
    
    def should_use_exact_match(self, query: str) -> bool:
        """Detect if query should use exact keyword matching.
        
        Very short queries or specific terms (proper nouns) may benefit
        from exact keyword matching rather than semantic search.
        
        Args:
            query: Query text
            
        Returns:
            True if exact match preferred, False for semantic search
        """
        if not query:
            return False
        
        words = query.strip().split()
        
        # Very short queries (< 2 words) might need exact match
        if len(words) < 2:
            return True
        
        # Check for proper nouns (capitalized words that aren't at start of sentence)
        # This is a heuristic - proper nouns often need exact matching
        proper_nouns = [w for w in words[1:] if w[0].isupper()]
        if len(proper_nouns) > 0:
            logger.debug(f"Query contains proper nouns, may benefit from exact match: {proper_nouns}")
            return True
        
        return False
    
    def rewrite_query_for_embedding(self, query: str, intent: PastReferenceIntent) -> str:
        """Rewrite query to improve embedding quality.
        
        Converts short or ambiguous queries into more descriptive forms
        that produce better embeddings.
        
        Args:
            query: Original query
            intent: Detected intent
            
        Returns:
            Rewritten query
        """
        if not query:
            return query
        
        query_lower = query.lower().strip()
        rewritten = query
        
        # Rewrite single-word topic queries
        if intent.intent_type == 'topic' and len(query_lower.split()) == 1:
            if intent.topics:
                # Use the topic with context
                rewritten = f"what did we discuss about {query}"
                logger.debug(f"Rewrote single-word topic query: '{query}' → '{rewritten}'")
        
        # Rewrite queries without past reference context
        if not any(phrase in query_lower for phrase in ['what did', 'tell me', 'remind me', 'discuss', 'talk']):
            if intent.intent_type == 'topic' and intent.topics:
                rewritten = f"what did we discuss about {query}"
                logger.debug(f"Added past reference context: '{query}' → '{rewritten}'")
        
        return rewritten


def expand_query_for_search(query: str, intent: PastReferenceIntent) -> str:
    """Convenience function to expand query for search.
    
    Args:
        query: Original query text
        intent: Detected intent
        
    Returns:
        Expanded query text
    """
    understanding = QueryUnderstanding()
    expanded = understanding.expand_query(query, intent)
    rewritten = understanding.rewrite_query_for_embedding(expanded, intent)
    return rewritten

