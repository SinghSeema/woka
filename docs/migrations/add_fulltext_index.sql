-- Add full-text search index on summary column
-- This enables fast keyword search using PostgreSQL's tsvector

-- Create GIN index for full-text search on summary column
CREATE INDEX IF NOT EXISTS idx_sessions_summary_fts 
ON sessions USING gin(to_tsvector('english', summary));

-- Add comment for documentation
COMMENT ON INDEX idx_sessions_summary_fts IS 'GIN index for full-text search on summary column using English text search vectors';

-- Optional: Create composite index for common query patterns (user + date)
-- This helps with queries that filter by user and date range
CREATE INDEX IF NOT EXISTS idx_sessions_user_date 
ON sessions (user_name, created_at DESC);

COMMENT ON INDEX idx_sessions_user_date IS 'Composite index for filtering by user_name and created_at (common query pattern)';

