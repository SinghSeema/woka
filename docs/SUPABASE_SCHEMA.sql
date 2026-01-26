-- Supabase migration for Woka Wellness sessions table
-- Run this in your Supabase SQL editor
-- This table stores session summaries for agentic memory

-- Enable pgvector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- Create sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    room_name TEXT NOT NULL,
    user_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    message_count INTEGER NOT NULL DEFAULT 0,
    embedding vector(384),  -- Vector embedding for semantic search (384 for local models like all-MiniLM-L6-v2, 1536 for OpenAI)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for faster queries by user_name
CREATE INDEX IF NOT EXISTS idx_sessions_user_name ON sessions(user_name);

-- Create index for faster queries by created_at
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC);

-- Create vector index for semantic search (using IVFFlat for approximate nearest neighbor search)
-- Note: This index requires at least some data in the table. If you get an error, insert a few rows first.
CREATE INDEX IF NOT EXISTS idx_sessions_embedding ON sessions 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Enable Row Level Security (RLS) - optional, for security
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

-- Create policy to allow all operations (adjust based on your security needs)
-- For free tier, you might want to allow all operations
CREATE POLICY "Allow all operations" ON sessions
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Optional: Create a function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to auto-update updated_at
CREATE TRIGGER update_sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE sessions IS 'Stores session summaries for agentic memory and continuity across conversations';
COMMENT ON COLUMN sessions.user_name IS 'Normalized user name (lowercase) for consistent lookups';
COMMENT ON COLUMN sessions.room_name IS 'Unique room/session identifier';
COMMENT ON COLUMN sessions.summary IS 'LLM-generated comprehensive session summary for context';
COMMENT ON COLUMN sessions.duration_seconds IS 'Session duration in seconds';
COMMENT ON COLUMN sessions.message_count IS 'Number of messages exchanged in the session';
COMMENT ON COLUMN sessions.created_at IS 'Timestamp when session was created';
COMMENT ON COLUMN sessions.updated_at IS 'Timestamp when record was last updated';
COMMENT ON COLUMN sessions.embedding IS 'Vector embedding for semantic search using pgvector';

-- Create function for semantic similarity search
-- This function allows searching for sessions by embedding similarity
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

