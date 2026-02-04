-- Debug version of hybrid_search_sessions to see why no matches are found
-- This version logs intermediate results to help diagnose issues
-- Run this in SQL Editor to test your query

-- IMPORTANT: Use the ACTUAL expanded query text from your application logs
-- Check logs for: "Topic query: expanded '...' → 'discussion about cardio...'"
-- Use that expanded query text here, NOT the original user query

-- Test query (replace with your actual values)
WITH test_params AS (
    SELECT 
        'discussion about cardio'::text AS query_text,  -- Use EXPANDED query from logs!
        -- NOTE: This uses a session embedding as placeholder - won't be accurate!
        -- For accurate results, you need the actual query embedding from your application
        -- To get it: Check logs for the embedding or generate it in Python
        (SELECT embedding FROM sessions WHERE embedding IS NOT NULL LIMIT 1)::vector(384) AS query_embedding,
        'wika'::text AS filter_user_name,
        ARRAY['cardio']::text[] AS filter_topics,
        0.5::float AS match_threshold  -- Same threshold as used in code
)
SELECT 
    s.id,
    s.user_name,
    LEFT(s.summary, 100) AS summary_preview,
    s.topics,
    -- Semantic similarity
    (1 - (s.embedding <=> test_params.query_embedding))::double precision AS similarity,
    -- Keyword score
    COALESCE(
        ts_rank(
            to_tsvector('english', s.summary),
            plainto_tsquery('english', test_params.query_text)
        )::double precision,
        0.0::double precision
    ) AS keyword_score,
    -- Combined score (same calculation as function: 0.7 * semantic + 0.3 * keyword)
    ((0.7 * (1 - (s.embedding <=> test_params.query_embedding))) +
     (0.3 * COALESCE(
         ts_rank(
             to_tsvector('english', s.summary),
             plainto_tsquery('english', test_params.query_text)
         )::double precision,
         0.0::double precision
     )))::double precision AS combined_score,
    -- Check if semantic match
    CASE 
        WHEN (1 - (s.embedding <=> test_params.query_embedding)) >= test_params.match_threshold 
        THEN '✅ SEMANTIC MATCH'
        ELSE '❌ Below threshold'
    END AS semantic_status,
    -- Check if keyword match
    CASE 
        WHEN to_tsvector('english', s.summary) @@ plainto_tsquery('english', test_params.query_text)
        THEN '✅ KEYWORD MATCH'
        ELSE '❌ No keyword match'
    END AS keyword_status,
    -- Check topic filter
    CASE 
        WHEN test_params.filter_topics IS NULL THEN 'N/A (no filter)'
        WHEN s.topics && test_params.filter_topics THEN '✅ Topic matches'
        ELSE '❌ Topic mismatch'
    END AS topic_status,
    -- Check if would be returned by function (meets all criteria)
    CASE 
        WHEN s.user_name = test_params.filter_user_name
         AND s.embedding IS NOT NULL
         AND (test_params.filter_topics IS NULL OR s.topics && test_params.filter_topics)
         AND (
             (1 - (s.embedding <=> test_params.query_embedding)) >= test_params.match_threshold OR
             to_tsvector('english', s.summary) @@ plainto_tsquery('english', test_params.query_text)
         )
        THEN '✅ WOULD BE RETURNED'
        ELSE '❌ FILTERED OUT'
    END AS function_result
FROM sessions s, test_params
WHERE 
    s.user_name = test_params.filter_user_name
    AND s.embedding IS NOT NULL
ORDER BY combined_score DESC
LIMIT 2;  -- Show only top 2 sessions

-- This will show you:
-- 1. What similarity scores you're getting
-- 2. What keyword scores you're getting
-- 3. Combined score (weighted: 70% semantic + 30% keyword)
-- 4. Whether semantic threshold (0.5) is met
-- 5. Whether keyword search matches
-- 6. Whether topic filter matches
-- 7. Whether the session would be returned by the function

-- NOTE: The query_embedding used here is a placeholder (from a session).
-- For accurate results, you need the ACTUAL query embedding generated from "discussion about cardio"
-- The similarity scores here will NOT match production because embeddings are different!
-- 
-- To get accurate results:
-- 1. Check your application logs for the actual query text being used
-- 2. Generate the embedding for that query text in Python
-- 3. Replace the query_embedding in this query with the actual embedding
