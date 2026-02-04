-- Migration: Add topics column and GIN index for topic-based filtering
-- Run this in your Supabase SQL editor
-- Date: 2024-01-XX

-- Step 1: Add topics column as TEXT array (nullable initially for backward compatibility)
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS topics TEXT[];

-- Step 2: Add comment for documentation
COMMENT ON COLUMN sessions.topics IS 'Array of wellness topics discussed in this session (e.g., ["sleep", "nutrition", "exercise"]). Used for fast topic-based filtering with GIN index.';

-- Step 3: Create GIN index for fast array containment and overlap queries
-- This enables fast queries like:
--   WHERE topics @> ARRAY['sleep']  -- Contains 'sleep'
--   WHERE topics && ARRAY['sleep', 'nutrition']  -- Overlaps with any topic
CREATE INDEX IF NOT EXISTS idx_sessions_topics_gin 
ON sessions USING gin(topics);

-- Step 4: Optional - Update match_sessions function to support topic filtering
-- (This will be done in a separate migration if needed)

-- Verification queries (run after migration):
-- SELECT column_name, data_type FROM information_schema.columns 
--   WHERE table_name = 'sessions' AND column_name = 'topics';
-- 
-- SELECT indexname, indexdef FROM pg_indexes 
--   WHERE tablename = 'sessions' AND indexname = 'idx_sessions_topics_gin';

