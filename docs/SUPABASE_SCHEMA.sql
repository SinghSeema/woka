-- Supabase migration for Woka Wellness sessions table
-- Run this in your Supabase SQL editor
-- This table stores session summaries for agentic memory

-- Create sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    room_name TEXT NOT NULL,
    user_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for faster queries by user_name
CREATE INDEX IF NOT EXISTS idx_sessions_user_name ON sessions(user_name);

-- Create index for faster queries by created_at
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC);

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

