-- Add structured metadata column to sessions table
-- Stores GOAL, PROGRESS, COMMITMENTS, UNRESOLVED, CONSTRAINTS alongside the prose summary
-- The prose summary is kept for semantic search quality; metadata enables structured recall

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT NULL;

-- Index for querying sessions that have commitments (future follow-up queries)
CREATE INDEX IF NOT EXISTS idx_sessions_metadata ON sessions USING GIN (metadata);

-- Verify
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'sessions' AND column_name = 'metadata';
