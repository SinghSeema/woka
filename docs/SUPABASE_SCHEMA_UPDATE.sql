-- Migration script to update embedding dimension from 1536 to 384
-- Run this if you're using a local embedding model (e.g., all-MiniLM-L6-v2)
-- that generates 384-dimensional embeddings

-- Step 1: Drop the existing vector index
DROP INDEX IF EXISTS idx_sessions_embedding;

-- Step 2: Drop the match_sessions function (it references the old dimension)
DROP FUNCTION IF EXISTS match_sessions(vector(1536), float, int, text);

-- Step 3: Alter the embedding column to 384 dimensions
-- Note: This will remove existing embeddings, but that's okay since they were wrong dimension anyway
ALTER TABLE sessions DROP COLUMN IF EXISTS embedding;
ALTER TABLE sessions ADD COLUMN embedding vector(384);

-- Step 4: Recreate the vector index
CREATE INDEX IF NOT EXISTS idx_sessions_embedding ON sessions 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Step 5: Recreate the match_sessions function with 384 dimensions
CREATE OR REPLACE FUNCTION match_sessions(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    filter_user_name text DEFAULT NULL
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
    similarity float
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
        1 - (s.embedding <=> query_embedding) AS similarity
    FROM sessions s
    WHERE 
        s.embedding IS NOT NULL
        AND (filter_user_name IS NULL OR s.user_name = filter_user_name)
        AND (1 - (s.embedding <=> query_embedding)) >= match_threshold
    ORDER BY s.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

