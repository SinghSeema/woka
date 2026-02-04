-- Add embedding_model column to track which model generated embeddings
-- This enables versioning and batch re-embedding when models change

ALTER TABLE sessions
ADD COLUMN IF NOT EXISTS embedding_model TEXT;

-- Add comment for documentation
COMMENT ON COLUMN sessions.embedding_model IS 'Model used to generate the embedding (e.g., "all-MiniLM-L6-v2", "text-embedding-3-small"). Used for versioning and batch re-embedding.';

-- Optional: Create index for filtering by embedding model
CREATE INDEX IF NOT EXISTS idx_sessions_embedding_model 
ON sessions(embedding_model) 
WHERE embedding_model IS NOT NULL;

COMMENT ON INDEX idx_sessions_embedding_model IS 'Index for filtering sessions by embedding model (useful for batch re-embedding)';

