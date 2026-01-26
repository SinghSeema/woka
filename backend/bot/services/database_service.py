"""Supabase database service for session history."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.embedding_service import generate_embedding

logger = get_logger(__name__)

# Initialize Supabase client lazily
_supabase_client = None


def get_supabase_client():
    """Get or create Supabase client.

    Returns:
        Supabase client instance or None if not configured
    """
    global _supabase_client

    if not settings.SUPABASE_ENABLED:
        logger.debug("Supabase disabled in settings")
        return None

    if _supabase_client is None:
        try:
            from supabase import create_client, Client

            if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
                logger.error("❌ Supabase enabled but URL or KEY not configured")
                logger.error(f"   SUPABASE_URL: {'SET' if settings.SUPABASE_URL else 'NOT SET'}")
                logger.error(f"   SUPABASE_KEY: {'SET' if settings.SUPABASE_KEY else 'NOT SET'}")
                return None

            logger.info("🔌 Initializing Supabase client...")
            logger.info(f"   URL: {settings.SUPABASE_URL}")
            logger.info(f"   Key: {'SET' if settings.SUPABASE_KEY else 'NOT SET'} (length: {len(settings.SUPABASE_KEY) if settings.SUPABASE_KEY else 0})")
            
            _supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            logger.info("✅ Supabase client initialized successfully")
        except ImportError:
            logger.error("❌ supabase package not installed. Install with: pip install supabase")
            return None
        except Exception as e:
            logger.error(f"❌ Error initializing Supabase client: {e}", exc_info=True)
            return None

    return _supabase_client


async def save_session_summary(
    user_name: str,
    room_name: str,
    summary: str,
    duration_seconds: float,
    message_count: int,
) -> bool:
    """Save session summary to Supabase.

    Args:
        user_name: User's display name
        room_name: Room name
        summary: Session summary text
        duration_seconds: Session duration
        message_count: Number of messages

    Returns:
        True if saved successfully, False otherwise
    """
    logger.info(f"save_session_summary called: user={user_name}, room={room_name}, SUPABASE_ENABLED={settings.SUPABASE_ENABLED}")
    
    if not settings.SUPABASE_ENABLED:
        logger.warning("❌ Supabase disabled in settings, skipping session save")
        return False

    client = get_supabase_client()
    if not client:
        logger.error("❌ Supabase client not available, cannot save session summary")
        logger.error("   Check SUPABASE_URL and SUPABASE_KEY in .env file")
        return False

    try:
        # Normalize user name for consistent lookups
        normalized_name = user_name.lower().strip()
        
        # Validate inputs
        if not summary or len(summary.strip()) < 10:
            logger.warning(f"❌ Summary too short or empty, not saving (length: {len(summary) if summary else 0})")
            return False
        
        if not room_name:
            logger.warning("❌ Room name is empty, not saving session")
            return False

        # Generate embedding for semantic search if enabled
        embedding = None
        if settings.ENABLE_SEMANTIC_SEARCH:
            logger.info(f"🔄 Generating embedding for session summary (length: {len(summary)} chars)")
            try:
                embedding = await generate_embedding(summary.strip())
                if embedding:
                    actual_dim = len(embedding)
                    expected_dim = settings.EMBEDDING_DIMENSION
                    if actual_dim != expected_dim:
                        logger.error(
                            f"❌ Embedding dimension mismatch: got {actual_dim}, but database schema expects {expected_dim}. "
                            f"Update EMBEDDING_DIMENSION in config or database schema to match. "
                            f"Saving without embedding to avoid error."
                        )
                        embedding = None
                    else:
                        logger.info(f"✅ Generated embedding for session summary ({actual_dim} dimensions, matches schema)")
                else:
                    logger.warning("⚠️  Failed to generate embedding, saving without embedding")
            except Exception as e:
                logger.error(f"❌ Error generating embedding: {e}, saving without embedding", exc_info=True)

        # Match the schema: room_name, user_name, summary, duration_seconds, message_count, embedding
        # created_at and updated_at are auto-managed by the database
        data = {
            "room_name": room_name,
            "user_name": normalized_name,
            "summary": summary.strip(),
            "duration_seconds": int(duration_seconds),
            "message_count": message_count,
            # created_at and updated_at are handled by database defaults and triggers
        }
        
        # Add embedding if available
        if embedding:
            data["embedding"] = embedding

        logger.info(f"Inserting into 'sessions' table: {data}")
        result = client.table("sessions").insert(data).execute()
        
        if result.data:
            logger.info(
                f"✅ Successfully saved session summary to Supabase for {user_name} "
                f"(room: {room_name}, duration: {int(duration_seconds)}s, messages: {message_count})"
            )
            logger.info(f"   Inserted record ID: {result.data[0].get('id', 'unknown')}")
            return True
        else:
            logger.error(f"❌ Session summary insert returned no data for {user_name}")
            logger.error(f"   Response: {result}")
            return False

    except Exception as e:
        logger.error(
            f"❌ Error saving session summary to Supabase for {user_name} (room: {room_name}): {e}",
            exc_info=True
        )
        return False


async def get_past_sessions(user_name: str, limit: int = 2) -> List[Dict[str, Any]]:
    """Get past session summaries for a user.

    Args:
        user_name: User's display name
        limit: Maximum number of sessions to retrieve (default: 2)

    Returns:
        List of session summary dictionaries, ordered by most recent first
    """
    if not settings.SUPABASE_ENABLED:
        logger.debug("Supabase disabled, returning empty past sessions")
        return []

    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client not available, cannot retrieve past sessions")
        return []

    try:
        # Normalize user name for consistent lookups
        normalized_name = user_name.lower().strip()
        
        if not normalized_name:
            logger.warning("User name is empty, cannot retrieve past sessions")
            return []

        result = (
            client.table("sessions")
            .select("*")
            .eq("user_name", normalized_name)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        sessions = result.data if result.data else []
        
        if sessions:
            logger.info(
                f"✅ Retrieved {len(sessions)} past sessions for {user_name} "
                f"(requested: {limit})"
            )
            # Log details of retrieved sessions
            for i, session in enumerate(sessions[:3], 1):  # Log first 3
                summary = session.get("summary", "")
                created_at = session.get("created_at", "")
                room_name = session.get("room_name", "unknown")
                date_str = created_at[:10] if created_at and len(created_at) >= 10 else "unknown"
                logger.info(
                    f"   Session {i}: {date_str} (room: {room_name}, "
                    f"summary: {len(summary)} chars)"
                )
        else:
            logger.info(f"ℹ️  No past sessions found for {user_name} - new user or no history")
        
        return sessions

    except Exception as e:
        logger.error(
            f"Error retrieving past sessions from Supabase for {user_name}: {e}",
            exc_info=True
        )
        return []


async def check_session_exists(room_name: str) -> bool:
    """Check if a session with this room name already exists.

    Args:
        room_name: Room name to check

    Returns:
        True if session exists, False otherwise
    """
    if not settings.SUPABASE_ENABLED:
        return False

    client = get_supabase_client()
    if not client:
        return False

    try:
        result = (
            client.table("sessions")
            .select("id")
            .eq("room_name", room_name)
            .limit(1)
            .execute()
        )

        return len(result.data) > 0 if result.data else False

    except Exception as e:
        logger.error(f"Error checking session existence: {e}", exc_info=True)
        return False


async def get_sessions_by_semantic_search(
    user_name: str,
    query_text: str,
    limit: int = 5,
    threshold: float = 0.7
) -> List[Dict[str, Any]]:
    """Get sessions using semantic similarity search.
    
    Args:
        user_name: User's display name
        query_text: Query text to search for
        limit: Maximum number of sessions to retrieve
        threshold: Minimum similarity threshold (0.0 to 1.0)
        
    Returns:
        List of session dictionaries ordered by similarity score
    """
    if not settings.SUPABASE_ENABLED or not settings.ENABLE_SEMANTIC_SEARCH:
        logger.debug("Semantic search disabled, falling back to keyword search")
        return []
    
    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client not available, cannot perform semantic search")
        return []
    
    try:
        # Generate embedding for query
        query_embedding = await generate_embedding(query_text)
        if not query_embedding:
            logger.warning("Failed to generate query embedding, falling back to keyword search")
            return []
        
        # Normalize user name
        normalized_name = user_name.lower().strip()
        
        # Use the match_sessions function for semantic search
        result = client.rpc(
            "match_sessions",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit,
                "filter_user_name": normalized_name
            }
        ).execute()
        
        sessions = result.data if result.data else []
        
        if sessions:
            logger.info(
                f"✅ Semantic search found {len(sessions)} relevant sessions for '{query_text[:50]}...' "
                f"(threshold: {threshold})"
            )
            # Log similarity scores
            for i, session in enumerate(sessions[:3], 1):
                similarity = session.get("similarity", 0.0)
                logger.info(f"   Session {i}: similarity={similarity:.3f}")
        else:
            logger.info(f"ℹ️  No sessions found above threshold {threshold} for semantic search")
        
        return sessions
        
    except Exception as e:
        logger.error(
            f"Error performing semantic search for {user_name}: {e}",
            exc_info=True
        )
        return []


async def get_sessions_by_date_range(
    user_name: str,
    start_date: datetime,
    end_date: datetime
) -> List[Dict[str, Any]]:
    """Get sessions within a date range.
    
    Args:
        user_name: User's display name
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        
    Returns:
        List of session dictionaries ordered by most recent first
    """
    if not settings.SUPABASE_ENABLED:
        logger.debug("Supabase disabled, returning empty sessions")
        return []
    
    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client not available, cannot retrieve sessions by date")
        return []
    
    try:
        normalized_name = user_name.lower().strip()
        
        # Format dates for Supabase (ISO format)
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        result = (
            client.table("sessions")
            .select("*")
            .eq("user_name", normalized_name)
            .gte("created_at", start_str)
            .lte("created_at", end_str)
            .order("created_at", desc=True)
            .execute()
        )
        
        sessions = result.data if result.data else []
        
        if sessions:
            logger.info(
                f"✅ Retrieved {len(sessions)} sessions for {user_name} "
                f"between {start_date.date()} and {end_date.date()}"
            )
        else:
            logger.info(f"ℹ️  No sessions found for {user_name} in date range")
        
        return sessions
        
    except Exception as e:
        logger.error(
            f"Error retrieving sessions by date range for {user_name}: {e}",
            exc_info=True
        )
        return []


async def get_sessions_by_topic(
    user_name: str,
    topic_keywords: List[str],
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Get sessions by topic keywords (text search).
    
    Args:
        user_name: User's display name
        topic_keywords: List of keywords to search for
        limit: Maximum number of sessions to retrieve
        
    Returns:
        List of session dictionaries ordered by most recent first
    """
    if not settings.SUPABASE_ENABLED:
        logger.debug("Supabase disabled, returning empty sessions")
        return []
    
    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client not available, cannot search by topic")
        return []
    
    try:
        normalized_name = user_name.lower().strip()
        
        if not topic_keywords:
            logger.warning("No topic keywords provided")
            return []
        
        # Build query with OR conditions for each keyword
        query = (
            client.table("sessions")
            .select("*")
            .eq("user_name", normalized_name)
        )
        
        # Use text search - search in summary field
        # Supabase PostgREST doesn't support full-text search directly,
        # so we'll filter client-side or use ilike for simple matching
        # For better results, we could use PostgreSQL full-text search
        keyword_filter = "|".join(topic_keywords)
        query = query.ilike("summary", f"%{keyword_filter}%")
        
        result = (
            query
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        
        sessions = result.data if result.data else []
        
        # Filter sessions that contain any of the keywords
        filtered_sessions = []
        summary_lower = None
        for session in sessions:
            summary = session.get("summary", "").lower()
            if any(keyword.lower() in summary for keyword in topic_keywords):
                filtered_sessions.append(session)
        
        if filtered_sessions:
            logger.info(
                f"✅ Found {len(filtered_sessions)} sessions for {user_name} "
                f"with topics: {', '.join(topic_keywords)}"
            )
        else:
            logger.info(f"ℹ️  No sessions found for {user_name} with topics: {', '.join(topic_keywords)}")
        
        return filtered_sessions[:limit]
        
    except Exception as e:
        logger.error(
            f"Error searching sessions by topic for {user_name}: {e}",
            exc_info=True
        )
        return []


async def get_all_sessions(user_name: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all sessions for a user (with limit).
    
    Args:
        user_name: User's display name
        limit: Maximum number of sessions to retrieve
        
    Returns:
        List of session dictionaries ordered by most recent first
    """
    if not settings.SUPABASE_ENABLED:
        logger.debug("Supabase disabled, returning empty sessions")
        return []
    
    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client not available, cannot retrieve all sessions")
        return []
    
    try:
        normalized_name = user_name.lower().strip()
        
        result = (
            client.table("sessions")
            .select("*")
            .eq("user_name", normalized_name)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        
        sessions = result.data if result.data else []
        
        if sessions:
            logger.info(
                f"✅ Retrieved {len(sessions)} sessions for {user_name} "
                f"(requested: {limit})"
            )
        else:
            logger.info(f"ℹ️  No sessions found for {user_name}")
        
        return sessions
        
    except Exception as e:
        logger.error(
            f"Error retrieving all sessions for {user_name}: {e}",
            exc_info=True
        )
        return []


async def get_session_by_id(session_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific session by ID.
    
    Args:
        session_id: Session UUID
        
    Returns:
        Session dictionary or None if not found
    """
    if not settings.SUPABASE_ENABLED:
        logger.debug("Supabase disabled, cannot retrieve session by ID")
        return None
    
    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client not available, cannot retrieve session by ID")
        return None
    
    try:
        result = (
            client.table("sessions")
            .select("*")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )
        
        if result.data and len(result.data) > 0:
            logger.debug(f"✅ Retrieved session by ID: {session_id}")
            return result.data[0]
        else:
            logger.debug(f"ℹ️  Session not found: {session_id}")
            return None
        
    except Exception as e:
        logger.error(f"Error retrieving session by ID {session_id}: {e}", exc_info=True)
        return None

