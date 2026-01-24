"""Supabase database service for session history."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

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

        # Match the schema: room_name, user_name, summary, duration_seconds, message_count
        # created_at and updated_at are auto-managed by the database
        data = {
            "room_name": room_name,
            "user_name": normalized_name,
            "summary": summary.strip(),
            "duration_seconds": int(duration_seconds),
            "message_count": message_count,
            # created_at and updated_at are handled by database defaults and triggers
        }

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


async def get_past_sessions(user_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get past session summaries for a user.

    Args:
        user_name: User's display name
        limit: Maximum number of sessions to retrieve (default: 10)

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

