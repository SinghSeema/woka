-- Migration: Add chunk question index for semantic recall
-- Run this in your Supabase SQL editor
-- Requires pgvector extension

-- Step 0: Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- Step 1: Create table to store chunk-level questions and embeddings
CREATE TABLE IF NOT EXISTS session_chunk_questions (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    room_name text NOT NULL,
    user_name text NOT NULL,
    chunk_index integer NOT NULL,
    question_text text NOT NULL,
    chunk_text text NOT NULL,
    topics text[] DEFAULT ARRAY[]::text[],
    question_embedding vector(384),
    created_at timestamptz DEFAULT now()
);

-- Step 2: Indexes for fast filtering
CREATE INDEX IF NOT EXISTS idx_chunk_questions_user_name
ON session_chunk_questions (user_name);

CREATE INDEX IF NOT EXISTS idx_chunk_questions_room_name
ON session_chunk_questions (room_name);

CREATE INDEX IF NOT EXISTS idx_chunk_questions_topics_gin
ON session_chunk_questions USING gin(topics);

-- Optional: vector index for similarity search (tune lists for your dataset)
CREATE INDEX IF NOT EXISTS idx_chunk_questions_embedding
ON session_chunk_questions USING ivfflat (question_embedding vector_cosine_ops)
WITH (lists = 100);

-- Step 3: Matching function for semantic search
CREATE OR REPLACE FUNCTION match_chunk_questions(
    query_embedding vector(384),
    filter_user_name text,
    match_threshold float DEFAULT 0.7,
    limit_count int DEFAULT 5,
    filter_topics text[] DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    room_name text,
    user_name text,
    chunk_index integer,
    question_text text,
    chunk_text text,
    topics text[],
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        q.id,
        q.room_name,
        q.user_name,
        q.chunk_index,
        q.question_text,
        q.chunk_text,
        q.topics,
        (1 - (q.question_embedding <=> query_embedding))::double precision AS similarity
    FROM session_chunk_questions q
    WHERE 
        q.user_name = filter_user_name
        AND q.question_embedding IS NOT NULL
        AND (
          filter_topics IS NULL OR EXISTS (
            SELECT 1
            FROM unnest(q.topics) t
            JOIN unnest(filter_topics) f
              ON lower(t) = lower(f)
          )
        )
        AND (1 - (q.question_embedding <=> query_embedding)) >= match_threshold
    ORDER BY similarity DESC
    LIMIT limit_count;
END;
$$;

COMMENT ON FUNCTION match_chunk_questions IS 'Semantic search over chunk questions with optional topic filtering.';

-- Step 4: Join chunk matches with sessions (server-side join)
CREATE OR REPLACE FUNCTION match_chunk_questions_with_sessions(
    query_embedding vector(384),
    filter_user_name text,
    match_threshold float DEFAULT 0.7,
    limit_count int DEFAULT 5,
    filter_topics text[] DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    room_name text,
    user_name text,
    chunk_index integer,
    question_text text,
    chunk_text text,
    topics text[],
    similarity float,
    session_summary text,
    session_created_at timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        q.id,
        q.room_name,
        q.user_name,
        q.chunk_index,
        q.question_text,
        q.chunk_text,
        q.topics,
        (1 - (q.question_embedding <=> query_embedding))::double precision AS similarity,
        s.summary AS session_summary,
        s.created_at AS session_created_at
    FROM session_chunk_questions q
    JOIN sessions s
      ON s.room_name = q.room_name
     AND s.user_name = q.user_name
    WHERE 
        q.user_name = filter_user_name
        AND q.question_embedding IS NOT NULL
        AND (
          filter_topics IS NULL OR EXISTS (
            SELECT 1
            FROM unnest(q.topics) t
            JOIN unnest(filter_topics) f
              ON lower(t) = lower(f)
          )
        )
        AND (1 - (q.question_embedding <=> query_embedding)) >= match_threshold
    ORDER BY similarity DESC
    LIMIT limit_count;
END;
$$;

COMMENT ON FUNCTION match_chunk_questions_with_sessions IS 'Semantic search over chunk questions joined to session summaries.';

-- Step 5: Topic-only join for chunk questions (no embeddings needed)
CREATE OR REPLACE FUNCTION match_chunk_questions_by_topics(
    filter_user_name text,
    limit_count int DEFAULT 5,
    filter_topics text[] DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    room_name text,
    user_name text,
    chunk_index integer,
    question_text text,
    chunk_text text,
    topics text[],
    session_summary text,
    session_created_at timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        q.id,
        q.room_name,
        q.user_name,
        q.chunk_index,
        q.question_text,
        q.chunk_text,
        q.topics,
        s.summary AS session_summary,
        s.created_at AS session_created_at
    FROM session_chunk_questions q
    JOIN sessions s
      ON s.room_name = q.room_name
     AND s.user_name = q.user_name
    WHERE 
        q.user_name = filter_user_name
        AND (
          filter_topics IS NULL OR EXISTS (
            SELECT 1
            FROM unnest(q.topics) t
            JOIN unnest(filter_topics) f
              ON lower(t) = lower(f)
          )
        )
    ORDER BY s.created_at DESC
    LIMIT limit_count;
END;
$$;

COMMENT ON FUNCTION match_chunk_questions_by_topics IS 'Topic-only retrieval of chunk questions joined to session summaries.';

