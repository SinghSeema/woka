-- Quick verification: Check if hybrid_search_sessions function exists
-- Run this in Supabase SQL Editor

SELECT 
    '✅ Function EXISTS' AS status,
    p.proname AS function_name,
    pg_get_function_arguments(p.oid) AS arguments
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = 'public' 
  AND p.proname = 'hybrid_search_sessions';

-- If you see a row above, the function exists!
-- If no rows, the function wasn't created - re-run the migration.
