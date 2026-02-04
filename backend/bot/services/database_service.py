"""Supabase database service for session history."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Numpy is available through sentence-transformers dependency
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


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not HAS_NUMPY:
        # Fallback to manual calculation if numpy not available
        try:
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm_a = sum(a * a for a in vec1) ** 0.5
            norm_b = sum(b * b for b in vec2) ** 0.5
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            similarity = dot_product / (norm_a * norm_b)
            return max(0.0, min(1.0, similarity))
        except Exception as e:
            logger.debug(f"Error calculating cosine similarity (fallback): {e}")
            return 0.0
    
    try:
        # Convert to numpy arrays for efficient computation
        a = np.array(vec1)
        b = np.array(vec2)
        
        # Calculate cosine similarity
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        similarity = dot_product / (norm_a * norm_b)
        # Ensure result is between 0 and 1
        return max(0.0, min(1.0, similarity))
    except Exception as e:
        logger.debug(f"Error calculating cosine similarity: {e}")
        return 0.0


async def search_cached_embeddings(
    query_embedding: List[float],
    cached_embeddings: List[Dict[str, Any]],
    threshold: float = 0.7,
    limit: int = 5,
    user_name: str = None,
    query_text: str = None  # Optional: for diagnostic logging
) -> List[Dict[str, Any]]:
    """Search cached embeddings locally using cosine similarity.
    
    OPTIMIZATION: Do similarity search locally instead of querying Supabase.
    This is MUCH faster (no network call) when embeddings are cached.
    
    Args:
        query_embedding: Query embedding vector
        cached_embeddings: List of dicts with 'summary' and 'embedding' keys
        threshold: Minimum similarity threshold
        limit: Maximum number of results
        user_name: Optional user name to fetch full session data if needed
        
    Returns:
        List of matching sessions with similarity scores
    """
    if not query_embedding or not cached_embeddings:
        logger.debug(f"Cannot search: query_embedding={bool(query_embedding)}, cached_embeddings={len(cached_embeddings) if cached_embeddings else 0}")
        return []
    
    try:
        query_embedding_dim = len(query_embedding) if query_embedding else 0
        
        # Calculate similarities and find matches
        matches = []
        all_similarities = []
        
        for i, item in enumerate(cached_embeddings, 1):
            summary = item.get("summary", "").strip()
            embedding = item.get("embedding")
            
            if not summary or not embedding:
                continue
            
            # Convert embedding to List[float] if needed (should already be parsed, but handle edge cases)
            if isinstance(embedding, str):
                logger.debug(f"Item {i}: Parsing string embedding (should have been parsed during fetch)")
                try:
                    import json
                    try:
                        embedding = json.loads(embedding)
                    except json.JSONDecodeError:
                        embedding_str = embedding.strip('[]')
                        embedding = [float(x.strip()) for x in embedding_str.split(',') if x.strip()]
                    
                    if not isinstance(embedding, list) or len(embedding) == 0:
                        raise ValueError(f"Parsed embedding is not a valid list")
                    
                    if len(embedding) != 384 and len(embedding) != 1536:
                        logger.warning(f"Item {i}: Unexpected embedding dimension: {len(embedding)}")
                except Exception as e:
                    logger.error(f"Item {i}: Failed to parse embedding: {e}")
                    continue
            elif not isinstance(embedding, (list, tuple)):
                try:
                    embedding = list(embedding) if hasattr(embedding, '__iter__') else None
                    if embedding is None:
                        continue
                except Exception as e:
                    logger.error(f"Item {i}: Failed to convert embedding: {e}")
                    continue
            
            embedding_dim = len(embedding) if embedding else 0
            
            if embedding_dim != query_embedding_dim:
                logger.debug(f"Item {i}: Dimension mismatch (query={query_embedding_dim}, stored={embedding_dim}), skipping")
                continue
            
            similarity = cosine_similarity(query_embedding, embedding)
            all_similarities.append(similarity)
            
            # Log cosine similarity score for each item (INFO level)
            summary_preview = summary[:80] + "..." if len(summary) > 80 else summary
            is_match = similarity >= threshold
            match_status = "✅ MATCHING" if is_match else "❌ NOT MATCHING"
            diff_from_threshold = similarity - threshold
            logger.info(
                f"🔍 [COSINE SIMILARITY] Score: {similarity:.4f} | Threshold: {threshold:.4f} | "
                f"Diff: {diff_from_threshold:+.4f} | Status: {match_status} | "
                f"Summary: '{summary_preview}'"
            )
            
            if similarity >= threshold:
                matches.append({
                    "summary": summary,
                    "similarity": similarity,
                    "embedding": embedding
                })
        
        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        matches = matches[:limit]
        
        max_similarity = max(all_similarities) if all_similarities else 0.0
        min_similarity = min(all_similarities) if all_similarities else 0.0
        avg_similarity = sum(all_similarities) / len(all_similarities) if all_similarities else 0.0
        
        if not matches:
            logger.info(
                f"❌ [SEMANTIC SEARCH] No matches found above threshold {threshold:.4f} | "
                f"Stats: max={max_similarity:.4f}, min={min_similarity:.4f}, avg={avg_similarity:.4f} | "
                f"Checked {len(all_similarities)} embeddings | All scores below threshold"
            )
            return []
        
        logger.info(
            f"✅ [SEMANTIC SEARCH] Found {len(matches)} matches above threshold {threshold:.4f} | "
            f"Max similarity: {max_similarity:.4f} | Checked {len(all_similarities)} embeddings"
        )
        
        # Log top matches with scores
        for i, match in enumerate(matches[:3], 1):  # Log top 3 matches
            logger.info(
                f"  📊 [TOP MATCH {i}] Cosine similarity: {match['similarity']:.4f} | "
                f"Summary: '{match['summary'][:80]}...'"
            )
        
        # Step 2: Fetch full session data for matches (if user_name provided)
        # This ensures we have all metadata (created_at, duration, etc.)
        if user_name and settings.SUPABASE_ENABLED:
            try:
                # Fetch full sessions by matching summaries
                # We'll get recent sessions and match by summary text
                full_sessions = await get_past_sessions(user_name, limit=limit * 2)
                
                # Match summaries to get full session data
                results = []
                summary_to_match = {m["summary"]: m for m in matches}
                
                for session in full_sessions:
                    session_summary = session.get("summary", "").strip()
                    if session_summary in summary_to_match:
                        match = summary_to_match[session_summary]
                        # Merge full session data with similarity score
                        session["similarity"] = match["similarity"]
                        session["cached"] = True  # Mark as from local cache
                        results.append(session)
                        if len(results) >= limit:
                            break
                
                if results:
                    logger.debug(f"Local embedding search found {len(results)} matches (from cache)")
                    return results
            except Exception as e:
                logger.debug(f"Error fetching full session data for local matches: {e}")
        
        # Return matches with summary only
        results = []
        for m in matches:
            results.append({
                "summary": m["summary"],
                "similarity": m["similarity"],
                "cached": True,
                "created_at": None,
                "duration_seconds": 0,
                "message_count": 0
            })
        
        return results
        
    except Exception as e:
        logger.error(f"Error searching cached embeddings: {e}", exc_info=True)
        return []


async def save_session_summary(
    user_name: str,
    room_name: str,
    summary: str,
    duration_seconds: float,
    message_count: int,
    topics: List[str] = None,
) -> bool:
    """Save session summary to Supabase.

    Args:
        user_name: User's display name
        room_name: Room name
        summary: Session summary text
        duration_seconds: Session duration
        message_count: Number of messages
        topics: Optional list of topics extracted from summary

    Returns:
        True if saved successfully, False otherwise
    """
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
            # Generate embedding for session summary (no verbose logging of vector contents)
            # Uses pre-loaded SentenceTransformer model (all-MiniLM-L6-v2)
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
                        # Log which model generated the embedding (for debugging, not stored in DB)
                        embedding_model = _get_current_embedding_model()
                        if embedding_model:
                            logger.debug(
                                f"✅ Embedding generated using model: {embedding_model} "
                                f"(dimension: {actual_dim}, pre-loaded SentenceTransformer)"
                            )
                else:
                    logger.warning("⚠️  Failed to generate embedding, saving without embedding")
            except Exception as e:
                logger.error(f"❌ Error generating embedding: {e}, saving without embedding", exc_info=True)

        # Match the schema: room_name, user_name, summary, duration_seconds, message_count, embedding, topics
        # created_at and updated_at are auto-managed by the database
        data = {
            "room_name": room_name,
            "user_name": normalized_name,
            "summary": summary.strip(),
            "duration_seconds": int(duration_seconds),
            "message_count": message_count,
            # created_at and updated_at are handled by database defaults and triggers
        }
        
        # Add topics if provided (even if empty list, store it)
        # Ensure topics is a list (not None)
        if topics is None:
            topics = []
        
        if topics:
            data["topics"] = topics
        else:
            # Store empty array instead of None
            data["topics"] = []
        
        # Add embedding if available (do not log full embedding contents)
        if embedding:
            data["embedding"] = embedding
            # Note: embedding_model is NOT stored in database - it's always the pre-loaded
            # SentenceTransformer model (all-MiniLM-L6-v2) as configured in settings

        # Cache embedding in embedding cache (optimization)
        from bot.services.embedding_service import _embedding_cache
        if _embedding_cache and embedding:
            _embedding_cache.set_embedding(summary.strip(), embedding)

        
        try:
            result = client.table("sessions").insert(data).execute()
        except Exception as insert_error:
            error_str = str(insert_error).lower()
            
            # Check if error is about missing topics column
            if "column" in error_str and "topics" in error_str:
                logger.error(
                    "❌ Topics column may not exist in database. "
                    "Please run migration: docs/migrations/add_topics_column.sql"
                )
                raise
            
            # Other errors
            else:
                logger.error(
                    f"❌ Database insert error for {user_name}: {insert_error}",
                    exc_info=True
                )
                raise
        
        if result.data:
            logger.info(
                f"✅ [SESSION SAVED] User: {user_name} | Room: {room_name} | "
                f"Topics: {len(topics) if topics else 0} | Duration: {int(duration_seconds)}s"
            )
            return True
        else:
            logger.error(
                f"❌ [SESSION SAVE] Insert returned no data | User: {user_name} | Room: {room_name}"
            )
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
            logger.debug(f"Retrieved {len(sessions)} past sessions for {user_name} (requested: {limit})")
        else:
            logger.debug(f"No past sessions found for {user_name}")
        
        return sessions

    except Exception as e:
        logger.error(
            f"Error retrieving past sessions from Supabase for {user_name}: {e}",
            exc_info=True
        )
        return []


async def get_past_session_embeddings(user_name: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Get past session embeddings for pre-warming embedding cache.
    
    OPTIMIZATION: Fetches only summary and embedding (not full session data).
    This is much lighter and faster than fetching full sessions.
    
    Args:
        user_name: User's display name
        limit: Maximum number of sessions to retrieve (default: 3)
        
    Returns:
        List of dictionaries with 'summary' and 'embedding' keys
    """
    if not settings.SUPABASE_ENABLED or not settings.ENABLE_SEMANTIC_SEARCH:
        logger.debug("Supabase or semantic search disabled, skipping embedding pre-warm")
        return []

    client = get_supabase_client()
    if not client:
        return []

    try:
        normalized_name = user_name.lower().strip()
        
        if not normalized_name:
            return []

        # OPTIMIZATION: Select only summary and embedding (not full session data)
        result = (
            client.table("sessions")
            .select("summary, embedding")  # Only what we need for embedding cache
            .eq("user_name", normalized_name)
            .not_.is_("embedding", "null")  # Only sessions with embeddings
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        embeddings_data = result.data if result.data else []
        
        if embeddings_data:
            logger.debug(f"Retrieved {len(embeddings_data)} session embeddings for {user_name}")
            # Parse embeddings once here (store as lists, not strings)
            parsed_count = 0
            for i, item in enumerate(embeddings_data):
                embedding = item.get("embedding")
                
                if embedding:
                    if isinstance(embedding, str):
                        try:
                            import json
                            try:
                                embedding = json.loads(embedding)
                                parsed_count += 1
                            except json.JSONDecodeError:
                                embedding_str = embedding.strip('[]')
                                embedding = [float(x.strip()) for x in embedding_str.split(',') if x.strip()]
                                parsed_count += 1
                            
                            if isinstance(embedding, list) and len(embedding) > 0:
                                item["embedding"] = embedding
                            else:
                                item["embedding"] = None
                        except Exception as e:
                            logger.debug(f"Embedding {i+1}: Failed to parse: {e}")
                            item["embedding"] = None
                    elif not isinstance(embedding, (list, tuple)):
                        try:
                            embedding = list(embedding) if hasattr(embedding, '__iter__') else None
                            if embedding:
                                item["embedding"] = embedding
                            else:
                                item["embedding"] = None
                        except Exception as e:
                            logger.debug(f"Embedding {i+1}: Conversion failed: {e}")
                            item["embedding"] = None
            
            embeddings_data = [item for item in embeddings_data if item.get("embedding") is not None]
            
            if parsed_count > 0:
                logger.debug(f"Parsed {parsed_count} string embeddings to lists")
        
        return embeddings_data

    except Exception as e:
        logger.error(
            f"Error retrieving session embeddings for {user_name}: {e}",
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


async def _expand_query_topics_with_semantic_matching(
    user_name: str,
    query_topics: List[str]
) -> List[str]:
    """Expand query topics by finding semantically similar stored topics.
    
    This handles cases where query uses synonyms (e.g., "drawing") but
    stored topics are consolidated (e.g., "art").
    
    Args:
        user_name: User's name
        query_topics: Topics extracted from user query
        
    Returns:
        List of stored topics that semantically match query topics
    """
    if not query_topics:
        return []
    
    try:
        from bot.services.llm_topic_extractor import match_topics_semantically
        
        # Get all unique stored topics for this user
        client = get_supabase_client()
        if not client:
            return query_topics  # Fallback to original topics
        
        normalized_name = user_name.lower().strip()
        
        # Get all sessions for this user to collect stored topics
        result = (
            client.table("sessions")
            .select("topics")
            .eq("user_name", normalized_name)
            .not_.is_("topics", "null")
            .execute()
        )
        
        # Collect all unique stored topics
        stored_topics_set = set()
        for session in (result.data or []):
            topics_list = session.get("topics", [])
            if topics_list:
                stored_topics_set.update([t.lower() for t in topics_list if t])
        
        stored_topics = list(stored_topics_set)
        
        if not stored_topics:
            return query_topics
        
        # Use semantic matching to find which stored topics match query topics
        matched_topics = await match_topics_semantically(
            query_topics=query_topics,
            stored_topics=stored_topics,
            similarity_threshold=0.7
        )
        
        # Combine query topics and matched topics (deduplicated)
        expanded_topics = list(set(query_topics + matched_topics))
        
        if matched_topics:
            logger.info(
                f"✅ [TOPIC EXPANSION] query={query_topics} → matched={matched_topics} → "
                f"expanded={expanded_topics}"
            )
        
        return expanded_topics
        
    except Exception as e:
        logger.warning(
            f"⚠️  [TOPIC EXPANSION] Error: {type(e).__name__}: {e}, using query topics as-is"
        )
        return query_topics


async def get_sessions_by_semantic_search(
    user_name: str,
    query_text: str,
    limit: int = 5,
    threshold: float = 0.7,
    topics: List[str] = None,
    date_range: Optional[Dict[str, datetime]] = None,
    shadow_memory = None  # Optional ShadowMemory instance for local search
) -> List[Dict[str, Any]]:
    """Get sessions using hybrid search (semantic + keyword + metadata filtering).
    
    Uses the hybrid_search_sessions() PostgreSQL function which combines:
    - Semantic similarity search (vector embeddings)
    - Keyword search (full-text search on summary)
    - Metadata filtering (topics, dates) using database indexes
    
    This replaces the sequential fallback approach with a single optimized query.
    
    Args:
        user_name: User's display name
        query_text: Query text to search for
        limit: Maximum number of sessions to retrieve
        threshold: Minimum similarity threshold (0.0 to 1.0) for semantic search
        topics: Optional list of topics for pre-filtering (uses indexed topic column)
        date_range: Optional dict with 'start' and 'end' datetime for date filtering
        shadow_memory: Optional ShadowMemory instance (for future local cache optimization)
        
    Returns:
        List of session dictionaries ordered by combined_score (descending)
    """
    if not settings.SUPABASE_ENABLED or not settings.ENABLE_SEMANTIC_SEARCH:
        logger.debug("Semantic search disabled")
        return []
    
    try:
        # Generate query embedding
        query_embedding = await generate_embedding(query_text)
        if not query_embedding:
            logger.warning(
                f"❌ [HYBRID SEARCH] Failed to generate embedding | "
                f"User: {user_name} | Query: '{query_text[:80]}...'"
            )
            return []
        
        # Get Supabase client
        client = get_supabase_client()
        if not client:
            return []
        
        normalized_name = user_name.lower().strip()
        
        # Prepare parameters for hybrid_search_sessions function
        params = {
            "query_text": query_text,
            "query_embedding": query_embedding,
            "filter_user_name": normalized_name,
            "match_threshold": threshold,
            "limit_count": limit,
            "semantic_weight": 0.7,  # 70% weight for semantic similarity
            "keyword_weight": 0.3,   # 30% weight for keyword matching
        }
        
        # Add optional filters with semantic topic expansion
        if topics:
            # Expand query topics using semantic matching to handle synonyms
            # e.g., query "drawing" → matches stored topic "art"
            expanded_topics = await _expand_query_topics_with_semantic_matching(
                user_name=normalized_name,
                query_topics=topics
            )
            params["filter_topics"] = expanded_topics
        
        if date_range:
            params["filter_date_from"] = date_range.get("start")
            params["filter_date_to"] = date_range.get("end")
        
        # Call hybrid_search_sessions RPC function
        logger.info(
            f"🔍 [HYBRID SEARCH] User: {user_name} | Query: '{query_text[:60]}...' | "
            f"Topics: {topics} | Threshold: {threshold:.3f}"
        )
        
        try:
            result = client.rpc("hybrid_search_sessions", params).execute()
            sessions = result.data if result.data else []
            
            # Ensure similarity is always a float (not None) for all sessions
            for session in sessions:
                similarity = session.get("similarity")
                if similarity is None:
                    # Critical: Log this as it indicates a database function issue
                    available_fields = list(session.keys())
                    logger.error(
                        f"❌ [HYBRID SEARCH] Session {session.get('id', 'unknown')[:8]}... missing 'similarity' field. "
                        f"Available: {available_fields}. Check hybrid_search_sessions function."
                    )
                    session["similarity"] = 0.0
                elif not isinstance(similarity, (int, float)):
                    try:
                        session["similarity"] = float(similarity)
                    except (ValueError, TypeError):
                        session["similarity"] = 0.0
                else:
                    session["similarity"] = float(similarity)
            
            if sessions:
                # Log top result with key metrics
                top_session = sessions[0]
                logger.info(
                    f"✅ [HYBRID SEARCH] Found {len(sessions)} sessions | "
                    f"Top: similarity={top_session.get('similarity', 0.0):.3f}, "
                    f"combined={top_session.get('combined_score', 0.0):.3f}"
                )
            else:
                logger.warning(
                    f"⚠️  [HYBRID SEARCH] No matches | User: {user_name} | "
                    f"Query: '{query_text[:60]}...' | Threshold: {threshold:.3f}"
                )
            
            return sessions
            
        except Exception as rpc_error:
            # Check if error is about function not found
            error_str = str(rpc_error)
            error_code = getattr(rpc_error, 'code', None) if hasattr(rpc_error, 'code') else None
            
            if (error_code == "PGRST202" or 
                ("hybrid_search_sessions" in error_str and "not found" in error_str.lower())):
                logger.warning(
                    f"⚠️  [HYBRID SEARCH] Function not found (PGRST202), falling back to match_sessions. "
                    f"Run migration: docs/migrations/hybrid_search_function.sql"
                )
                return await _fallback_to_match_sessions(
                    client, normalized_name, query_embedding, threshold, limit, topics, date_range
                )
            else:
                logger.error(
                    f"❌ [HYBRID SEARCH] RPC error: {type(rpc_error).__name__}: {rpc_error}",
                    exc_info=True
                )
                raise
        
    except Exception as e:
        logger.error(
            f"❌ [HYBRID SEARCH] Error: {type(e).__name__}: {e} | User: {user_name}",
            exc_info=True
        )
        return []


async def get_sessions_by_date_range(
    user_name: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Get sessions within a date range.
    
    Args:
        user_name: User's display name
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        limit: Maximum number of sessions to retrieve
        
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
        
        # Format dates for Supabase query
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        result = (
            client.table("sessions")
            .select("*")
            .eq("user_name", normalized_name)
            .gte("created_at", start_str)
            .lte("created_at", end_str)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        
        sessions = result.data if result.data else []
        
        
        return sessions
        
    except Exception as e:
        logger.error(
            f"Error retrieving sessions by date range for {user_name}: {e}",
            exc_info=True
        )
        return []


# _fallback_keyword_search function removed - replaced by hybrid_search_sessions()
# which combines semantic + keyword search in a single database query

async def _fallback_keyword_search_DEPRECATED(
    user_name: str,
    query_text: str,
    limit: int = 5,
    topics: List[str] = None
) -> List[Dict[str, Any]]:
    """Fallback keyword search when semantic search finds no matches.
    
    Searches for keywords from query text in session summaries.
    Uses simple text matching (case-insensitive).
    
    Args:
        user_name: User's display name
        query_text: Query text to extract keywords from
        limit: Maximum number of sessions to retrieve
        topics: Optional topics to also search for
        
    Returns:
        List of session dictionaries ordered by relevance
    """
    if not settings.SUPABASE_ENABLED:
        return []
    
    client = get_supabase_client()
    if not client:
        return []
    
    try:
        normalized_name = user_name.lower().strip()
        
        # Extract keywords from query text (remove stop words)
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'we', 'did', 'do', 'what', 'when', 'where', 'how', 'why', 'about', 'regarding', 'concerning',
            'related', 'discuss', 'discussed', 'talk', 'talked', 'mention', 'mentioned', 'say', 'said',
            'this', 'that', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must',
            'just', 'only', 'also', 'too', 'very', 'much', 'more', 'most', 'some', 'any',
            'past', 'previous', 'before', 'ago', 'last', 'time', 'times', 'session', 'conversation'
        }
        
        # Extract keywords from query
        query_words = query_text.lower().split()
        keywords = [w for w in query_words if len(w) > 2 and w not in stop_words]
        
        # Add topics if provided
        if topics:
            keywords.extend([t.lower() for t in topics if len(t) > 2])
        
        # Remove duplicates
        keywords = list(set(keywords))
        
        if not keywords:
            logger.debug("No keywords extracted for fallback search")
            return []
        
        logger.info(
            f"🔍 [KEYWORD SEARCH] Starting database query | "
            f"Keywords: {keywords} | User: {user_name} | Limit: {limit * 5}"
        )
        
        # Fetch recent sessions from database
        logger.info(
            f"📊 [DATABASE QUERY] Executing: SELECT * FROM sessions WHERE user_name = '{normalized_name}' "
            f"ORDER BY created_at DESC LIMIT {limit * 5}"
        )
        result = (
            client.table("sessions")
            .select("*")
            .eq("user_name", normalized_name)
            .order("created_at", desc=True)
            .limit(limit * 5)  # Get more to filter
            .execute()
        )
        
        all_sessions = result.data if result.data else []
        logger.info(
            f"📊 [DATABASE QUERY] Retrieved {len(all_sessions)} sessions from database | "
            f"Will filter by keyword matching in Python"
        )
        
        # Score sessions by keyword matches
        logger.info(
            f"🔍 [KEYWORD MATCHING] Scoring {len(all_sessions)} sessions by keyword matches | "
            f"Keywords to match: {keywords}"
        )
        scored_sessions = []
        for i, session in enumerate(all_sessions, 1):
            summary = session.get("summary", "").lower()
            score = 0
            matched_keywords = []
            
            for keyword in keywords:
                if keyword in summary:
                    score += 1
                    matched_keywords.append(keyword)
            
            if score > 0:
                logger.info(
                    f"  ✅ [KEYWORD MATCH {i}] Score: {score}/{len(keywords)} keywords matched | "
                    f"Matched: {matched_keywords} | Summary: '{summary[:80]}...'"
                )
                scored_sessions.append({
                    "session": session,
                    "score": score,
                    "matched_keywords": matched_keywords
                })
            else:
                logger.debug(
                    f"  ❌ [KEYWORD NO MATCH {i}] Score: 0/{len(keywords)} | "
                    f"No keywords found in summary"
                )
        
        # Sort by score (highest first)
        scored_sessions.sort(key=lambda x: x["score"], reverse=True)
        
        # Return top matches
        results = [item["session"] for item in scored_sessions[:limit]]
        
        if results:
            all_matched_keywords = set(
                kw for item in scored_sessions[:limit] 
                for kw in item['matched_keywords']
            )
            logger.info(
                f"✅ [KEYWORD SEARCH] Found {len(results)} sessions | "
                f"Total scored: {len(scored_sessions)} | "
                f"Matched keywords: {', '.join(sorted(all_matched_keywords))} | "
                f"Top score: {scored_sessions[0]['score']}/{len(keywords)}"
            )
        else:
            logger.info(
                f"❌ [KEYWORD SEARCH] No sessions matched any keywords | "
                f"Searched {len(all_sessions)} sessions | Keywords: {keywords}"
            )
        
        return results
        
    except Exception as e:
        logger.error(f"Error in keyword search fallback: {e}", exc_info=True)
        return []


async def get_sessions_by_topic(
    user_name: str,
    topics: List[str],
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Get sessions containing specific topics using indexed topic column.
    
    Uses GIN index on topics array for fast filtering. Falls back to summary text
    search if topics column is not available (backward compatibility).
    
    Args:
        user_name: User's display name
        topics: List of topic keywords to search for
        limit: Maximum number of sessions to retrieve
        
    Returns:
        List of session dictionaries ordered by most recent first
    """
    if not settings.SUPABASE_ENABLED:
        logger.debug("Supabase disabled, returning empty sessions")
        return []
    
    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client not available, cannot retrieve sessions by topic")
        return []
    
    if not topics:
        return []
    
    try:
        normalized_name = user_name.lower().strip()
        normalized_topics = [t.lower().strip() for t in topics if t and t.strip()]
        
        if not normalized_topics:
            return []
        
        logger.debug(f"Searching for topics: {normalized_topics} (limit={limit}, user={user_name})")
        
        # Try indexed topic search first (if topics column exists)
        try:
            # Use Supabase array overlap operator (&&) - uses GIN index
            # This finds sessions where topics array overlaps with search topics
            result = (
                client.table("sessions")
                .select("*")
                .eq("user_name", normalized_name)
                .overlaps("topics", normalized_topics)  # Array overlap - uses GIN index
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            sessions = result.data if result.data else []
            
            # get_sessions_by_topic doesn't return similarity (it's not a semantic search)
            # Set similarity to None explicitly so context_injector knows it's N/A
            for session in sessions:
                if "similarity" not in session:
                    session["similarity"] = None
            
            if sessions:
                logger.debug(f"Found {len(sessions)} sessions using topic index for topics: {', '.join(normalized_topics)}")
                return sessions
            else:
                logger.debug(f"No sessions found using topic index, trying fallback search")
        except Exception as e:
            # Fallback if topics column doesn't exist or query fails
            logger.debug(f"Topic index query failed (may not exist yet): {e}, using fallback")
        
        # Fallback: Search in summary text (backward compatibility)
        result = (
            client.table("sessions")
            .select("*")
            .eq("user_name", normalized_name)
            .order("created_at", desc=True)
            .limit(limit * 5)
            .execute()
        )
        
        all_sessions = result.data if result.data else []
        
        # Filter by topics in summary text (case-insensitive)
        matching_sessions = []
        for session in all_sessions:
            summary = session.get("summary", "").lower()
            for topic in normalized_topics:
                if topic in summary:
                    matching_sessions.append(session)
                    break
                if len(matching_sessions) >= limit:
                    break
            if len(matching_sessions) >= limit:
                break
        
        sessions = matching_sessions
        
        # get_sessions_by_topic doesn't return similarity (it's not a semantic search)
        # Set similarity to None explicitly so context_injector knows it's N/A
        for session in sessions:
            if "similarity" not in session:
                session["similarity"] = None
        
        if sessions:
            logger.debug(f"Found {len(sessions)} sessions using fallback search for topics: {', '.join(normalized_topics)}")
        else:
            logger.debug(f"No sessions found for {user_name} with topics: {', '.join(normalized_topics)}")
        
        return sessions
        
    except Exception as e:
        logger.error(
            f"Error retrieving sessions by topic for {user_name}: {e}",
            exc_info=True
        )
        return []


async def get_all_sessions(user_name: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Get all sessions for a user (most recent first).
    
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
            logger.debug(f"Retrieved {len(sessions)} sessions for {user_name} (requested: {limit})")
        else:
            logger.debug(f"No sessions found for {user_name}")
        
        return sessions
        
    except Exception as e:
        logger.error(
            f"Error retrieving all sessions for {user_name}: {e}",
            exc_info=True
        )
        return []


async def _fallback_to_match_sessions(
    client,
    user_name: str,
    query_embedding: List[float],
    threshold: float,
    limit: int,
    topics: Optional[List[str]] = None,
    date_range: Optional[Dict[str, datetime]] = None
) -> List[Dict[str, Any]]:
    """Fallback to old match_sessions function if hybrid_search_sessions is not available.
    
    This provides backward compatibility until migrations are run.
    
    Args:
        client: Supabase client
        user_name: Normalized user name
        query_embedding: Query embedding vector
        threshold: Similarity threshold
        limit: Result limit
        topics: Optional topics for post-filtering
        date_range: Optional date range for post-filtering
        
    Returns:
        List of session dictionaries
    """
    try:
        logger.debug("Using fallback match_sessions function")
        
        # Use old match_sessions function
        result = client.rpc(
            "match_sessions",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit * 2,  # Get more to filter
                "filter_user_name": user_name
            }
        ).execute()
        
        sessions = result.data if result.data else []
        
        # Post-filter by topics if provided (client-side filtering)
        if topics and sessions:
            topic_lower = [t.lower() for t in topics]
            filtered_sessions = []
            for session in sessions:
                session_topics = session.get("topics", [])
                if session_topics and any(t.lower() in topic_lower for t in session_topics):
                    filtered_sessions.append(session)
                elif not session_topics:
                    # Fallback: check summary text if topics column not populated
                    summary = session.get("summary", "").lower()
                    if any(t in summary for t in topic_lower):
                        filtered_sessions.append(session)
            sessions = filtered_sessions[:limit]
        
        # Post-filter by date range if provided
        if date_range and sessions:
            start_date = date_range.get("start")
            end_date = date_range.get("end")
            filtered_sessions = []
            for session in sessions:
                created_at_str = session.get("created_at")
                if created_at_str:
                    try:
                        from datetime import datetime
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        if start_date and created_at < start_date:
                            continue
                        if end_date and created_at > end_date:
                            continue
                        filtered_sessions.append(session)
                    except Exception:
                        # If date parsing fails, include the session
                        filtered_sessions.append(session)
                else:
                    filtered_sessions.append(session)
            sessions = filtered_sessions[:limit]
        
        if sessions:
            logger.info(
                f"✅ [FALLBACK SEARCH] Found {len(sessions)} sessions using match_sessions "
                f"(threshold: {threshold:.4f})"
            )
        else:
            logger.info(
                f"❌ [FALLBACK SEARCH] No matches found using match_sessions "
                f"(threshold: {threshold:.4f})"
            )
        
        return sessions
        
    except Exception as e:
        logger.error(f"Error in fallback match_sessions: {e}", exc_info=True)
        return []


async def _fallback_to_match_sessions(
    client,
    user_name: str,
    query_embedding: List[float],
    threshold: float,
    limit: int,
    topics: Optional[List[str]] = None,
    date_range: Optional[Dict[str, datetime]] = None
) -> List[Dict[str, Any]]:
    """Fallback to old match_sessions function if hybrid_search_sessions is not available.
    
    This provides backward compatibility until migrations are run.
    
    Args:
        client: Supabase client
        user_name: Normalized user name
        query_embedding: Query embedding vector
        threshold: Similarity threshold
        limit: Result limit
        topics: Optional topics for post-filtering
        date_range: Optional date range for post-filtering
        
    Returns:
        List of session dictionaries
    """
    try:
        logger.debug("Using fallback match_sessions function")
        
        # Use old match_sessions function
        result = client.rpc(
            "match_sessions",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit * 2,  # Get more to filter
                "filter_user_name": user_name
            }
        ).execute()
        
        sessions = result.data if result.data else []
        
        # Post-filter by topics if provided (client-side filtering)
        if topics and sessions:
            topic_lower = [t.lower() for t in topics]
            filtered_sessions = []
            for session in sessions:
                session_topics = session.get("topics", [])
                if session_topics and any(t.lower() in topic_lower for t in session_topics):
                    filtered_sessions.append(session)
                elif not session_topics:
                    # Fallback: check summary text if topics column not populated
                    summary = session.get("summary", "").lower()
                    if any(t in summary for t in topic_lower):
                        filtered_sessions.append(session)
            sessions = filtered_sessions[:limit]
        
        # Post-filter by date range if provided
        if date_range and sessions:
            start_date = date_range.get("start")
            end_date = date_range.get("end")
            filtered_sessions = []
            for session in sessions:
                created_at_str = session.get("created_at")
                if created_at_str:
                    try:
                        from datetime import datetime
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        if start_date and created_at < start_date:
                            continue
                        if end_date and created_at > end_date:
                            continue
                        filtered_sessions.append(session)
                    except Exception:
                        # If date parsing fails, include the session
                        filtered_sessions.append(session)
                else:
                    filtered_sessions.append(session)
            sessions = filtered_sessions[:limit]
        
        if sessions:
            logger.info(
                f"✅ [FALLBACK SEARCH] Found {len(sessions)} sessions using match_sessions "
                f"(threshold: {threshold:.4f})"
            )
        else:
            logger.info(
                f"❌ [FALLBACK SEARCH] No matches found using match_sessions "
                f"(threshold: {threshold:.4f})"
            )
        
        return sessions
        
    except Exception as e:
        logger.error(f"Error in fallback match_sessions: {e}", exc_info=True)
        return []


def _get_current_embedding_model() -> Optional[str]:
    """Get the name of the current embedding model.
    
    This returns the actual model name being used, which should match
    the pre-loaded SentenceTransformer model (all-MiniLM-L6-v2).
    
    Returns:
        Model name string (e.g., "all-MiniLM-L6-v2", "text-embedding-3-small") or None
    """
    if not settings.ENABLE_SEMANTIC_SEARCH:
        return None
    
    # Determine which model is being used
    use_local = (
        settings.EMBEDDING_MODEL == "local" or 
        not settings.EMBEDDING_MODEL.startswith("text-embedding") or
        not getattr(settings, 'OPENAI_API_KEY', None)
    )
    
    if use_local:
        # Return the local model name from settings (defaults to all-MiniLM-L6-v2)
        # This should match the pre-loaded SentenceTransformer model
        model_name = getattr(settings, 'LOCAL_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
        logger.debug(f"Using local embedding model: {model_name}")
        return model_name
    else:
        # Return OpenAI model name
        model_name = settings.EMBEDDING_MODEL
        logger.debug(f"Using OpenAI embedding model: {model_name}")
        return model_name


async def batch_generate_embeddings_for_sessions(
    user_name: Optional[str] = None,
    limit: int = 100,
    model_name: Optional[str] = None
) -> Dict[str, Any]:
    """Batch generate embeddings for sessions that don't have embeddings.
    
    Useful for:
    - Backfilling embeddings for old sessions
    - Re-embedding when model changes
    - Fixing sessions with missing embeddings
    
    Args:
        user_name: Optional user name to filter sessions (None = all users)
        limit: Maximum number of sessions to process
        model_name: Optional model name to filter by (None = current model)
        
    Returns:
        Dict with statistics: {"processed": int, "successful": int, "failed": int, "skipped": int}
    """
    if not settings.SUPABASE_ENABLED or not settings.ENABLE_SEMANTIC_SEARCH:
        logger.warning("Supabase or semantic search disabled, cannot batch generate embeddings")
        return {"processed": 0, "successful": 0, "failed": 0, "skipped": 0}
    
    client = get_supabase_client()
    if not client:
        logger.error("Supabase client not available")
        return {"processed": 0, "successful": 0, "failed": 0, "skipped": 0}
    
    try:
        current_model = _get_current_embedding_model()
        if not current_model:
            logger.error("Cannot determine current embedding model")
            return {"processed": 0, "successful": 0, "failed": 0, "skipped": 0}
        
        # Build query to find sessions without embeddings or with different model
        query = client.table("sessions").select("id, summary, embedding_model")
        
        if user_name:
            query = query.eq("user_name", user_name.lower().strip())
        
        # Filter: no embedding OR embedding_model is NULL OR embedding_model != current_model
        # Note: Supabase doesn't support OR directly, so we'll fetch and filter in Python
        query = query.is_("embedding", "null").limit(limit * 2)  # Get more to filter
        
        result = query.execute()
        all_sessions = result.data if result.data else []
        
        # Filter sessions that need embeddings
        sessions_to_process = []
        for session in all_sessions:
            session_model = session.get("embedding_model")
            has_embedding = session.get("embedding") is not None
            
            # Process if: no embedding OR different model OR explicitly requested model
            if not has_embedding:
                sessions_to_process.append(session)
            elif model_name and session_model != model_name:
                sessions_to_process.append(session)
            elif not model_name and session_model != current_model:
                sessions_to_process.append(session)
            
            if len(sessions_to_process) >= limit:
                break
        
        if not sessions_to_process:
            logger.info("No sessions need embedding generation")
            return {"processed": 0, "successful": 0, "failed": 0, "skipped": len(all_sessions)}
        
        logger.info(
            f"Batch generating embeddings for {len(sessions_to_process)} sessions "
            f"(model: {current_model})"
        )
        
        stats = {"processed": 0, "successful": 0, "failed": 0, "skipped": 0}
        
        for session in sessions_to_process:
            session_id = session.get("id")
            summary = session.get("summary", "")
            
            if not summary or len(summary.strip()) < 10:
                logger.debug(f"Skipping session {session_id}: summary too short")
                stats["skipped"] += 1
                continue
            
            try:
                # Generate embedding
                embedding = await generate_embedding(summary.strip())
                if not embedding:
                    logger.warning(f"Failed to generate embedding for session {session_id}")
                    stats["failed"] += 1
                    continue
                
                # Update session with embedding and model
                update_data = {
                    "embedding": embedding,
                    "embedding_model": current_model
                }
                
                client.table("sessions").update(update_data).eq("id", session_id).execute()
                
                stats["successful"] += 1
                stats["processed"] += 1
                
                if stats["processed"] % 10 == 0:
                    logger.info(
                        f"Progress: {stats['processed']}/{len(sessions_to_process)} "
                        f"(successful: {stats['successful']}, failed: {stats['failed']})"
                    )
                    
            except Exception as e:
                logger.error(f"Error processing session {session_id}: {e}", exc_info=True)
                stats["failed"] += 1
                stats["processed"] += 1
        
        logger.info(
            f"Batch embedding generation complete: "
            f"processed={stats['processed']}, successful={stats['successful']}, "
            f"failed={stats['failed']}, skipped={stats['skipped']}"
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Error in batch embedding generation: {e}", exc_info=True)
        return {"processed": 0, "successful": 0, "failed": 0, "skipped": 0}
