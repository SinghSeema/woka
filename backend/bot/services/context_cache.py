"""In-memory cache for past session queries."""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Cache entry for query results."""
    sessions: List[Dict[str, Any]]
    timestamp: datetime = field(default_factory=datetime.now)
    query_key: str = ""


class ContextCache:
    """In-memory cache for past session queries."""
    
    def __init__(self, ttl_seconds: int = 300):
        """Initialize cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self._cache: Dict[str, Dict[str, CacheEntry]] = {}  # {user_name: {query_key: CacheEntry}}
        self._ttl = timedelta(seconds=ttl_seconds)
        logger.info(f"Initialized context cache with TTL: {ttl_seconds}s")
    
    def get(
        self,
        user_name: str,
        query_key: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached sessions for a query.
        
        Args:
            user_name: User's name
            query_key: Cache key for the query
            
        Returns:
            Cached sessions or None if not found/expired
        """
        normalized_name = user_name.lower().strip()
        
        if normalized_name not in self._cache:
            return None
        
        user_cache = self._cache[normalized_name]
        
        if query_key not in user_cache:
            return None
        
        entry = user_cache[query_key]
        
        # Check if expired
        if datetime.now() - entry.timestamp > self._ttl:
            logger.debug(f"Cache entry expired for {user_name}: {query_key}")
            del user_cache[query_key]
            return None
        
        logger.debug(f"Cache hit for {user_name}: {query_key}")
        return entry.sessions
    
    def set(
        self,
        user_name: str,
        query_key: str,
        sessions: List[Dict[str, Any]]
    ) -> None:
        """Cache query results.
        
        Args:
            user_name: User's name
            query_key: Cache key for the query
            sessions: Sessions to cache
        """
        normalized_name = user_name.lower().strip()
        
        if normalized_name not in self._cache:
            self._cache[normalized_name] = {}
        
        entry = CacheEntry(
            sessions=sessions.copy(),
            timestamp=datetime.now(),
            query_key=query_key
        )
        
        self._cache[normalized_name][query_key] = entry
        logger.debug(f"Cached {len(sessions)} sessions for {user_name}: {query_key}")
    
    def invalidate_user(self, user_name: str) -> None:
        """Invalidate all cache entries for a user.
        
        Args:
            user_name: User's name
        """
        normalized_name = user_name.lower().strip()
        
        if normalized_name in self._cache:
            count = len(self._cache[normalized_name])
            del self._cache[normalized_name]
            logger.info(f"Invalidated {count} cache entries for {user_name}")
    
    def clear(self) -> None:
        """Clear all cache entries."""
        total_entries = sum(len(cache) for cache in self._cache.values())
        self._cache.clear()
        logger.info(f"Cleared {total_entries} cache entries")
    
    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.
        
        Returns:
            Number of entries removed
        """
        removed = 0
        now = datetime.now()
        
        for user_name, user_cache in list(self._cache.items()):
            expired_keys = [
                key for key, entry in user_cache.items()
                if now - entry.timestamp > self._ttl
            ]
            
            for key in expired_keys:
                del user_cache[key]
                removed += 1
            
            # Remove user entry if empty
            if not user_cache:
                del self._cache[user_name]
        
        if removed > 0:
            logger.debug(f"Cleaned up {removed} expired cache entries")
        
        return removed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        total_entries = sum(len(cache) for cache in self._cache.values())
        total_users = len(self._cache)
        
        return {
            "total_entries": total_entries,
            "total_users": total_users,
            "ttl_seconds": self._ttl.total_seconds()
        }


def generate_cache_key(
    intent_type: str,
    query_text: Optional[str] = None,
    date_range: Optional[Dict[str, datetime]] = None,
    topics: Optional[List[str]] = None
) -> str:
    """Generate cache key for a query.
    
    Args:
        intent_type: Type of intent (semantic, date, topic, etc.)
        query_text: Query text (for semantic search)
        date_range: Date range (for date queries)
        topics: Topic keywords (for topic queries)
        
    Returns:
        Cache key string
    """
    parts = [f"type:{intent_type}"]
    
    if query_text:
        # Use first 50 chars of query for key
        parts.append(f"query:{query_text[:50].lower().strip()}")
    
    if date_range:
        start = date_range.get("start")
        end = date_range.get("end")
        if start and end:
            parts.append(f"date:{start.date()}:{end.date()}")
    
    if topics:
        parts.append(f"topics:{','.join(sorted(topics)).lower()}")
    
    return "|".join(parts)

