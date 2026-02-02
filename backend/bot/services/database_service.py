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
        logger.warning(
            f"⚠️  [FLOW-STEP-2] Cannot search: query_embedding={bool(query_embedding)}, "
            f"cached_embeddings={len(cached_embeddings) if cached_embeddings else 0}"
        )
        return []
    
    try:
        # DIAGNOSTIC: Check query embedding format
        query_embedding_type = type(query_embedding).__name__
        query_embedding_dim = len(query_embedding) if query_embedding else 0
        query_embedding_sample = query_embedding[:3] if query_embedding and len(query_embedding) >= 3 else []
        
        # DIAGNOSTIC: Check query embedding norm (should be ~1.0 if normalized)
        import numpy as np
        query_norm = np.linalg.norm(np.array(query_embedding)) if HAS_NUMPY and query_embedding else 0.0
        query_mean = np.mean(np.array(query_embedding)) if HAS_NUMPY and query_embedding else 0.0
        query_std = np.std(np.array(query_embedding)) if HAS_NUMPY and query_embedding else 0.0
        
        logger.info(
            f"🔍 [FLOW-STEP-2] Starting similarity search: "
            f"query_embedding_dim={query_embedding_dim}, "
            f"query_embedding_type={query_embedding_type}, "
            f"query_norm={query_norm:.3f} (should be ~1.0 if normalized), "
            f"query_mean={query_mean:.4f}, query_std={query_std:.4f}, "
            f"cached_embeddings_count={len(cached_embeddings)}, "
            f"threshold={threshold}"
        )
        
        # Step 1: Calculate similarities and find matches
        matches = []
        all_similarities = []  # Track all similarities for diagnostics
        
        for i, item in enumerate(cached_embeddings, 1):
            summary = item.get("summary", "").strip()
            embedding = item.get("embedding")
            
            if not summary or not embedding:
                logger.debug(f"   Skipping item {i}: missing summary or embedding")
                continue
            
            # DIAGNOSTIC: Check stored embedding format
            embedding_type = type(embedding).__name__
            
            # Convert embedding to List[float] if needed (should already be parsed, but handle edge cases)
            if isinstance(embedding, str):
                logger.warning(
                    f"   ⚠️  Item {i}: Embedding is still a string (should have been parsed during fetch). "
                    f"Parsing now (len={len(embedding)})..."
                )
                try:
                    # Supabase pgvector might return as string like "[0.1,0.2,0.3]" or JSON
                    import json
                    # Try JSON first
                    try:
                        embedding = json.loads(embedding)
                        logger.info(f"   ✅ Item {i}: Parsed as JSON, dim={len(embedding) if isinstance(embedding, list) else 'N/A'}")
                    except json.JSONDecodeError:
                        # If not JSON, might be Python list string representation
                        # Remove brackets and split by comma
                        embedding_str = embedding.strip('[]')
                        # Count commas to estimate dimension
                        comma_count = embedding_str.count(',')
                        embedding = [float(x.strip()) for x in embedding_str.split(',') if x.strip()]
                        logger.info(f"   ✅ Item {i}: Parsed as comma-separated list, dim={len(embedding)} (comma_count={comma_count})")
                    
                    # Verify it's now a list of floats
                    if not isinstance(embedding, list) or len(embedding) == 0:
                        raise ValueError(f"Parsed embedding is not a valid list: {type(embedding)}, len={len(embedding) if hasattr(embedding, '__len__') else 'N/A'}")
                    
                    # Verify dimension is reasonable (should be 384 for local model)
                    if len(embedding) != 384 and len(embedding) != 1536:
                        logger.warning(
                            f"   ⚠️  Item {i}: Parsed embedding has unexpected dimension: {len(embedding)} "
                            f"(expected 384 or 1536). This might indicate a parsing issue."
                        )
                except Exception as e:
                    logger.error(
                        f"   ❌ Item {i}: Failed to parse embedding string: {e}, "
                        f"embedding_preview={str(embedding)[:200]}"
                    )
                    continue
            elif not isinstance(embedding, (list, tuple)):
                logger.warning(
                    f"   ⚠️  Item {i}: Unexpected embedding type: {embedding_type}, "
                    f"attempting to convert to list..."
                )
                try:
                    embedding = list(embedding) if hasattr(embedding, '__iter__') else None
                    if embedding is None:
                        logger.error(f"   ❌ Item {i}: Cannot convert embedding to list")
                        continue
                except Exception as e:
                    logger.error(f"   ❌ Item {i}: Failed to convert embedding: {e}")
                    continue
            
            # Calculate dimension AFTER parsing/conversion
            embedding_dim = len(embedding) if embedding else 0
            
            # Verify dimensions match
            if embedding_dim != query_embedding_dim:
                logger.warning(
                    f"   ⚠️  Item {i}: Dimension mismatch! "
                    f"query_dim={query_embedding_dim}, stored_dim={embedding_dim}, "
                    f"skipping this embedding"
                )
                continue
            
            # DIAGNOSTIC: Log embedding sample for first item
            if i == 1:
                embedding_sample = embedding[:3] if len(embedding) >= 3 else []
                logger.info(
                    f"   🔬 [DIAGNOSTIC] First cached embedding: "
                    f"type={embedding_type}, dim={embedding_dim}, "
                    f"sample={embedding_sample}, summary_len={len(summary)}"
                )
            
            # DIAGNOSTIC: Check vector norms (should be ~1.0 if normalized)
            import numpy as np
            query_norm = np.linalg.norm(np.array(query_embedding)) if HAS_NUMPY else sum(x*x for x in query_embedding)**0.5
            stored_norm = np.linalg.norm(np.array(embedding)) if HAS_NUMPY else sum(x*x for x in embedding)**0.5
            
            # DIAGNOSTIC: Check embedding statistics
            query_mean = np.mean(np.array(query_embedding)) if HAS_NUMPY else sum(query_embedding) / len(query_embedding)
            query_std = np.std(np.array(query_embedding)) if HAS_NUMPY else 0.0
            stored_mean = np.mean(np.array(embedding)) if HAS_NUMPY else sum(embedding) / len(embedding)
            stored_std = np.std(np.array(embedding)) if HAS_NUMPY else 0.0
            
            # Calculate cosine similarity
            similarity = cosine_similarity(query_embedding, embedding)
            all_similarities.append(similarity)  # Track for diagnostics
            
            # Log ALL similarity scores at INFO level to diagnose threshold issues
            summary_preview = summary[:100].replace("\n", " ").replace("\r", " ")
            
            # Log detailed diagnostics for first item or if similarity is interesting
            if i == 1 or similarity > 0.3:
                logger.info(
                    f"   📊 Item {i}/{len(cached_embeddings)}: similarity={similarity:.3f}, "
                    f"threshold={threshold}, match={'✅' if similarity >= threshold else '❌'}"
                )
                logger.info(
                    f"      🔬 [DIAGNOSTIC] Vector norms: query={query_norm:.3f}, stored={stored_norm:.3f} "
                    f"(should be ~1.0 if normalized)"
                )
                logger.info(
                    f"      🔬 [DIAGNOSTIC] Embedding stats: "
                    f"query_mean={query_mean:.4f}, query_std={query_std:.4f}, "
                    f"stored_mean={stored_mean:.4f}, stored_std={stored_std:.4f}"
                )
                logger.info(
                    f"      📝 Summary preview: '{summary_preview}...'"
                )
            else:
                # Less verbose for low similarity items
                logger.debug(
                    f"   📊 Item {i}/{len(cached_embeddings)}: similarity={similarity:.3f} "
                    f"(below threshold {threshold})"
                )
            
            if similarity >= threshold:
                matches.append({
                    "summary": summary,
                    "similarity": similarity,
                    "embedding": embedding  # Keep for reference
                })
                logger.info(
                    f"   ✅ Match {len(matches)}: similarity={similarity:.3f}, "
                    f"summary_preview='{summary[:80].replace(chr(10), ' ')}...'"
                )
        
        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        matches = matches[:limit]
        
        # Calculate max similarity for diagnostic purposes (even if below threshold)
        max_similarity = max(all_similarities) if all_similarities else 0.0
        
        logger.info(
            f"📊 [FLOW-STEP-2] Similarity search complete: "
            f"found {len(matches)} matches above threshold {threshold}, "
            f"max_similarity={max_similarity:.3f} (across all {len(cached_embeddings)} cached embeddings)"
        )
        
        if not matches:
            # DIAGNOSTIC: Analyze why similarity is low
            query_word_count = len(query_text.split()) if query_text else 0
            avg_summary_length = sum(len(item.get("summary", "")) for item in cached_embeddings) / len(cached_embeddings) if cached_embeddings else 0
            
            logger.warning(
                f"⚠️  [FLOW-STEP-2] No matches found above threshold {threshold}. "
                f"Highest similarity was {max_similarity:.3f}."
            )
            if query_text:
                logger.info(
                    f"   🔬 [DIAGNOSTIC] Query analysis: "
                    f"query_text='{query_text[:50]}...', query_word_count={query_word_count}, "
                    f"avg_summary_length={avg_summary_length:.0f} chars"
                )
                if query_word_count <= 2:
                    logger.warning(
                        f"   ⚠️  [ROOT CAUSE] Query is very short ({query_word_count} words). "
                        f"Single-word queries have sparse embeddings that don't match well with full summary embeddings. "
                        f"Consider: (1) expanding query (e.g., 'singing' → 'singing classes discussion'), "
                        f"(2) lowering threshold to {max(0.3, max_similarity - 0.1):.2f}, or (3) using keyword search."
                    )
                else:
                    logger.warning(
                        f"   ⚠️  [ROOT CAUSE] Low similarity despite reasonable query length. "
                        f"Possible issues: (1) embeddings not normalized, (2) different models used, "
                        f"(3) semantic mismatch. Consider lowering threshold or using keyword search."
                    )
            else:
                logger.warning(
                    f"   ⚠️  [ROOT CAUSE] Low similarity. "
                    f"avg_summary_length={avg_summary_length:.0f} chars. "
                    f"Possible issues: (1) embeddings not normalized, (2) different models used, "
                    f"(3) semantic mismatch. Consider lowering threshold or using keyword search."
                )
            return []
        
        logger.info(f"✅ [FLOW-STEP-2] Found {len(matches)} matches, extracting summary text...")
        for i, match in enumerate(matches, 1):
            summary = match.get("summary", "")
            similarity = match.get("similarity", 0.0)
            logger.info(
                f"   Match {i}: similarity={similarity:.3f}, "
                f"summary_len={len(summary)}, "
                f"summary_preview='{summary[:100].replace(chr(10), ' ')}...'"
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
                    logger.info(
                        f"✅ Local embedding search found {len(results)} matches "
                        f"(threshold: {threshold}, from cache, full data fetched)"
                    )
                    return results
            except Exception as e:
                logger.debug(f"Error fetching full session data for local matches: {e}")
                # Fall through to return matches with summary only
        
        # Step 3: Return matches with summary only (if full fetch failed or not requested)
        logger.info(
            f"📝 [FLOW-STEP-3] Extracting summary text from {len(matches)} matches..."
        )
        results = []
        for m in matches:
            summary_text = m["summary"]  # Extract summary text
            logger.debug(
                f"   Extracting summary: len={len(summary_text)}, "
                f"preview='{summary_text[:80].replace(chr(10), ' ')}...'"
            )
            results.append({
                "summary": summary_text,  # ← Summary text for prompt injection
                "similarity": m["similarity"],
                "cached": True,
                "created_at": None,  # Will default to "recent" in formatter
                "duration_seconds": 0,
                "message_count": 0
            })
        
        if results:
            logger.info(
                f"✅ [FLOW-STEP-3] Extracted {len(results)} summary texts ready for prompt injection"
            )
            for i, result in enumerate(results, 1):
                logger.info(
                    f"   Result {i}: summary_len={len(result['summary'])}, "
                    f"similarity={result['similarity']:.3f}"
                )
        
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
            # Generate embedding for session summary (no verbose logging of vector contents)
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
        
        # Add embedding if available (do not log full embedding contents)
        if embedding:
            data["embedding"] = embedding

        # ALSO cache embedding in embedding cache (optimization)
        from bot.services.embedding_service import _embedding_cache
        if _embedding_cache and embedding:
            _embedding_cache.set_embedding(summary.strip(), embedding)
            logger.debug(f"✅ Cached embedding for session summary ({len(summary)} chars)")

        # Log only high-level info, not full payload/embedding
        logger.info(
            f"Inserting session summary into 'sessions' table "
            f"(user={normalized_name}, room={room_name}, duration={int(duration_seconds)}s, messages={message_count}, "
            f"has_embedding={bool(embedding)})"
        )
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
            # Log details of retrieved sessions (high level only)
            for i, session in enumerate(sessions[:3], 1):  # Log first 3
                summary = session.get("summary", "")
                created_at = session.get("created_at", "")
                room_name = session.get("room_name", "unknown")
                date_str = created_at[:10] if created_at and len(created_at) >= 10 else "unknown"
                logger.info(
                    f"   Session {i}: {date_str} (room: {room_name}, "
                    f"summary: {len(summary)} chars)"
                )
            # Debug-level previews of summaries fetched from Supabase
            for i, s in enumerate(sessions[:3], 1):
                raw_summary = (s.get("summary", "") or "")
                summary_preview = raw_summary[:300].replace("\n", " ")
                logger.debug(
                    f"[past-context] Fetched past_session {i} summary preview "
                    f"(len={len(raw_summary)}): {summary_preview}"
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
            logger.info(
                f"✅ Retrieved {len(embeddings_data)} session embeddings for {user_name} "
                f"(for embedding cache pre-warm)"
            )
            # OPTIMIZATION: Parse embeddings once here (store as lists, not strings)
            # This prevents having to parse them on every similarity search
            parsed_count = 0
            for i, item in enumerate(embeddings_data):
                embedding = item.get("embedding")
                summary = item.get("summary", "")
                
                if embedding:
                    # Parse string embeddings to lists once
                    if isinstance(embedding, str):
                        try:
                            import json
                            try:
                                embedding = json.loads(embedding)
                                parsed_count += 1
                            except json.JSONDecodeError:
                                # If not JSON, might be Python list string representation
                                embedding_str = embedding.strip('[]')
                                embedding = [float(x.strip()) for x in embedding_str.split(',') if x.strip()]
                                parsed_count += 1
                            
                            # Verify it's now a list of floats
                            if isinstance(embedding, list) and len(embedding) > 0:
                                # Update the item with parsed embedding
                                item["embedding"] = embedding
                                logger.debug(
                                    f"   ✅ Parsed embedding {i+1}: dim={len(embedding)}, "
                                    f"summary_len={len(summary)}"
                                )
                            else:
                                logger.warning(
                                    f"   ⚠️  Embedding {i+1}: Parsed but invalid format, "
                                    f"removing from cache"
                                )
                                item["embedding"] = None
                        except Exception as e:
                            logger.warning(
                                f"   ⚠️  Embedding {i+1}: Failed to parse: {e}, "
                                f"removing from cache"
                            )
                            item["embedding"] = None
                    elif not isinstance(embedding, (list, tuple)):
                        logger.warning(
                            f"   ⚠️  Embedding {i+1}: Unexpected type {type(embedding).__name__}, "
                            f"attempting conversion"
                        )
                        try:
                            embedding = list(embedding) if hasattr(embedding, '__iter__') else None
                            if embedding:
                                item["embedding"] = embedding
                            else:
                                item["embedding"] = None
                        except Exception as e:
                            logger.warning(f"   ⚠️  Embedding {i+1}: Conversion failed: {e}")
                            item["embedding"] = None
            
            # Filter out items with invalid embeddings
            embeddings_data = [item for item in embeddings_data if item.get("embedding") is not None]
            
            if parsed_count > 0:
                logger.info(
                    f"✅ Parsed {parsed_count} string embeddings to lists "
                    f"(will be faster for similarity search)"
                )
            
            # DIAGNOSTIC: Log final format
            for i, item in enumerate(embeddings_data[:2], 1):
                embedding = item.get("embedding")
                summary = item.get("summary", "")
                if embedding:
                    embedding_type = type(embedding).__name__
                    embedding_dim = len(embedding) if hasattr(embedding, '__len__') else 0
                    logger.debug(
                        f"   🔬 Final embedding {i}: type={embedding_type}, dim={embedding_dim}, "
                        f"summary_len={len(summary)}"
                    )
        else:
            logger.debug(f"No session embeddings found for {user_name}")
        
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


async def get_sessions_by_semantic_search(
    user_name: str,
    query_text: str,
    limit: int = 5,
    threshold: float = 0.7,
    shadow_memory = None  # Optional ShadowMemory instance for local search
) -> List[Dict[str, Any]]:
    """Get sessions using semantic similarity search.
    
    OPTIMIZATION: First tries local cache (no DB query!), then falls back to Supabase.
    
    Args:
        user_name: User's display name
        query_text: Query text to search for
        limit: Maximum number of sessions to retrieve
        threshold: Minimum similarity threshold (0.0 to 1.0)
        shadow_memory: Optional ShadowMemory instance with cached embeddings
        
    Returns:
        List of session dictionaries ordered by similarity score
    """
    logger.info(
        f"🚀 [FLOW-ENTRY] Starting semantic search: "
        f"user={user_name}, query='{query_text[:50]}...', "
        f"limit={limit}, threshold={threshold}"
    )
    
    if not settings.SUPABASE_ENABLED or not settings.ENABLE_SEMANTIC_SEARCH:
        logger.warning("⚠️  [FLOW-ENTRY] Semantic search disabled, falling back to keyword search")
        return []
    
    try:
        # Step 1: Generate query embedding (check cache first)
        logger.info(f"🔑 [FLOW-STEP-1] Generating query embedding for: '{query_text[:50]}...'")
        query_embedding = await generate_embedding(query_text)
        if not query_embedding:
            logger.warning("❌ [FLOW-STEP-1] Failed to generate query embedding, falling back to keyword search")
            return []
        
        # DIAGNOSTIC: Check query embedding format
        query_embedding_type = type(query_embedding).__name__
        query_embedding_dim = len(query_embedding) if query_embedding else 0
        query_embedding_sample = query_embedding[:3] if query_embedding and len(query_embedding) >= 3 else []
        first_elem_type = type(query_embedding[0]).__name__ if query_embedding and len(query_embedding) > 0 else "N/A"
        
        logger.info(
            f"✅ [FLOW-STEP-1] Query embedding generated: "
            f"dim={query_embedding_dim}, type={query_embedding_type}, "
            f"sample={query_embedding_sample}, first_elem_type={first_elem_type}"
        )
        
        # Step 2: Try local cache first (OPTIMIZATION - no DB query!)
        if shadow_memory:
            logger.info(f"🔍 [FLOW-STEP-2] Checking Shadow Memory for cached embeddings...")
            cached_embeddings = shadow_memory.get_cached_embeddings()
            if cached_embeddings:
                logger.info(
                    f"✅ [FLOW-STEP-2] Found {len(cached_embeddings)} cached embeddings, "
                    f"performing local similarity search..."
                )
                local_results = await search_cached_embeddings(
                    query_embedding,
                    cached_embeddings,
                    threshold=threshold,
                    limit=limit,
                    user_name=user_name,  # For fetching full session data
                    query_text=query_text  # For diagnostic logging
                )
                
                if local_results:
                    logger.info(
                        f"✅ [FLOW-STEP-2] Local embedding search found {len(local_results)} matches "
                        f"(no Supabase vector search needed!)"
                    )
                    logger.info(
                        f"📋 [FLOW-STEP-3] Returning {len(local_results)} sessions with summary text "
                        f"ready for prompt injection"
                    )
                    for i, result in enumerate(local_results, 1):
                        summary = result.get("summary", "")
                        similarity = result.get("similarity", 0.0)
                        logger.info(
                            f"   Session {i}: similarity={similarity:.3f}, "
                            f"summary_len={len(summary)}, "
                            f"has_summary_text={'✅' if summary else '❌'}"
                        )
                    return local_results
            else:
                logger.info(f"ℹ️  [FLOW-STEP-2] No cached embeddings in Shadow Memory, will try Supabase")
        else:
            logger.info(f"ℹ️  [FLOW-STEP-2] Shadow Memory not available, will try Supabase")
        
        # Step 3: Fallback to Supabase query (if local cache doesn't have enough or not available)
        logger.info(f"🌐 [FLOW-STEP-2-FALLBACK] Falling back to Supabase vector search...")
        client = get_supabase_client()
        if not client:
            logger.warning("❌ [FLOW-STEP-2-FALLBACK] Supabase client not available, cannot perform semantic search")
            return []
        
        # Normalize user name
        normalized_name = user_name.lower().strip()
        
        # Use the match_sessions function for semantic search
        logger.info(f"🔍 [FLOW-STEP-2-FALLBACK] Querying Supabase with vector similarity search...")
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
                f"✅ [FLOW-STEP-2-FALLBACK] Supabase search found {len(sessions)} relevant sessions "
                f"for '{query_text[:50]}...' (threshold: {threshold})"
            )
            logger.info(
                f"📋 [FLOW-STEP-3] Extracting summary text from {len(sessions)} Supabase results..."
            )
            # Log similarity scores
            for i, session in enumerate(sessions[:3], 1):
                similarity = session.get("similarity", 0.0)
                logger.info(f"   Session {i}: similarity={similarity:.3f}")
            # Debug-level summary previews
            for i, s in enumerate(sessions[:3], 1):
                raw_summary = (s.get("summary", "") or "")
                summary_preview = raw_summary[:300].replace("\n", " ")
                logger.debug(
                    f"[past-context] Fetched semantic session {i} summary preview "
                    f"(len={len(raw_summary)}): {summary_preview}"
                )
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
        
        if sessions:
            logger.info(
                f"✅ Retrieved {len(sessions)} sessions for {user_name} "
                f"between {start_date.date()} and {end_date.date()}"
            )
            # Debug-level summary previews
            for i, s in enumerate(sessions[:3], 1):
                raw_summary = (s.get("summary", "") or "")
                summary_preview = raw_summary[:300].replace("\n", " ")
                logger.debug(
                    f"[past-context] Fetched date_range session {i} summary preview "
                    f"(len={len(raw_summary)}): {summary_preview}"
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
    topics: List[str],
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Get sessions containing specific topics (keyword search).
    
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
    
    try:
        normalized_name = user_name.lower().strip()
        
        # Build query with OR conditions for topics
        query = (
            client.table("sessions")
            .select("*")
            .eq("user_name", normalized_name)
        )
        
        # Add topic filters (OR condition - session contains any topic)
        if topics:
            logger.info(
                f"🔍 [TOPIC-SEARCH] Searching for topics: {topics} "
                f"(limit={limit}, user={user_name})"
            )
            # Supabase doesn't support OR directly, so we'll filter in Python
            # First get all sessions for user, then filter by topics
            # Get more sessions to increase chance of finding matches
            result = query.order("created_at", desc=True).limit(limit * 5).execute()
            all_sessions = result.data if result.data else []
            
            logger.info(
                f"📋 [TOPIC-SEARCH] Retrieved {len(all_sessions)} sessions from DB, "
                f"filtering for topics: {topics}"
            )
            
            # Filter by topics (case-insensitive)
            matching_sessions = []
            for session in all_sessions:
                summary = session.get("summary", "").lower()
                session_topics_found = []
                for topic in topics:
                    if topic.lower() in summary:
                        session_topics_found.append(topic)
                
                if session_topics_found:
                    logger.info(
                        f"✅ [TOPIC-SEARCH] Match found! Session contains topics: {session_topics_found}"
                    )
                    matching_sessions.append(session)
                    if len(matching_sessions) >= limit:
                        break
            
            if not matching_sessions:
                logger.warning(
                    f"⚠️  [TOPIC-SEARCH] No sessions found containing topics: {topics}"
                )
            
            sessions = matching_sessions
        else:
            sessions = []
        
        if sessions:
            logger.info(
                f"✅ [TOPIC-SEARCH] Successfully found {len(sessions)} sessions for {user_name} "
                f"containing topics: {', '.join(topics)}"
            )
            # Log summary previews at INFO level for visibility
            for i, s in enumerate(sessions[:3], 1):
                raw_summary = (s.get("summary", "") or "")
                summary_preview = raw_summary[:200].replace("\n", " ").replace("\r", " ")
                logger.info(
                    f"   📄 Session {i}/{len(sessions)}: summary_preview='{summary_preview}...' "
                    f"(len={len(raw_summary)})"
                )
        else:
            logger.warning(
                f"⚠️  [TOPIC-SEARCH] No sessions found for {user_name} with topics: {', '.join(topics)}"
            )
        
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
            logger.info(
                f"✅ Retrieved {len(sessions)} sessions for {user_name} "
                f"(requested: {limit})"
            )
            # Debug-level summary previews
            for i, s in enumerate(sessions[:3], 1):
                raw_summary = (s.get("summary", "") or "")
                summary_preview = raw_summary[:300].replace("\n", " ")
                logger.debug(
                    f"[past-context] Fetched all_sessions {i} summary preview "
                    f"(len={len(raw_summary)}): {summary_preview}"
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
