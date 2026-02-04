-- Hybrid search function for sessions
-- Combines semantic (vector) search + keyword (full-text) search + metadata filtering
-- This replaces the sequential fallback approach with a single optimized query

CREATE OR REPLACE FUNCTION hybrid_search_sessions(
    query_text text,
    query_embedding vector(384),
    filter_user_name text,
    filter_topics text[] DEFAULT NULL,
    filter_date_from timestamptz DEFAULT NULL,
    filter_date_to timestamptz DEFAULT NULL,
    semantic_weight float DEFAULT 0.7,
    keyword_weight float DEFAULT 0.3,
    match_threshold float DEFAULT 0.3,
    limit_count int DEFAULT 5
)
RETURNS TABLE (
    id uuid,
    room_name text,
    user_name text,
    summary text,
    duration_seconds integer,
    message_count integer,
    created_at timestamptz,
    updated_at timestamptz,
    topics text[],
    similarity float,
    keyword_score float,
    combined_score float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id,
        s.room_name,
        s.user_name,
        s.summary,
        s.duration_seconds,
        s.message_count,
        s.created_at,
        s.updated_at,
        s.topics,
        -- Semantic similarity (cosine distance converted to similarity)
        -- Cast to double precision to match function return type
        (1 - (s.embedding <=> query_embedding))::double precision AS similarity,
        -- Keyword score (ts_rank for full-text search)
        -- Cast to double precision to match function return type
        COALESCE(
            ts_rank(
                to_tsvector('english', s.summary),
                plainto_tsquery('english', query_text)
            )::double precision,
            0.0::double precision
        ) AS keyword_score,
        -- Combined score (weighted combination)
        -- Cast to double precision to match function return type
        ((semantic_weight * (1 - (s.embedding <=> query_embedding))) +
        (keyword_weight * COALESCE(
            ts_rank(
                to_tsvector('english', s.summary),
                plainto_tsquery('english', query_text)
            )::double precision,
            0.0::double precision
        )))::double precision AS combined_score
    FROM sessions s
    WHERE 
        s.user_name = filter_user_name
        AND s.embedding IS NOT NULL
        -- Metadata filtering (uses indexes)
        AND (filter_topics IS NULL OR s.topics && filter_topics)
        AND (filter_date_from IS NULL OR s.created_at >= filter_date_from)
        AND (filter_date_to IS NULL OR s.created_at <= filter_date_to)
        -- Either semantic match OR keyword match (parallel search)
        AND (
            (1 - (s.embedding <=> query_embedding)) >= match_threshold OR
            to_tsvector('english', s.summary) @@ plainto_tsquery('english', query_text)
        )
    ORDER BY combined_score DESC
    LIMIT limit_count;
END;
$$;

-- Add comment for documentation
COMMENT ON FUNCTION hybrid_search_sessions IS 'Hybrid search combining semantic (vector) and keyword (full-text) search with metadata filtering. Returns results ranked by combined score.';

