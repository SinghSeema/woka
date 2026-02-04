# Verifying and Refreshing Hybrid Search Function

## Important: It's a Function, Not a Table

`hybrid_search_sessions` is a **PostgreSQL function** (stored procedure), not a table. Functions don't appear in the table list - they're stored in the database's function catalog.

## Step 1: Verify the Function Exists

Run this query in your Supabase SQL Editor to check if the function was created:

```sql
-- Check if hybrid_search_sessions function exists
SELECT 
    p.proname AS function_name,
    pg_get_function_arguments(p.oid) AS arguments,
    pg_get_function_result(p.oid) AS return_type
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = 'public' 
  AND p.proname = 'hybrid_search_sessions';
```

**Expected Result**: If the function exists, you should see one row with:
- `function_name`: `hybrid_search_sessions`
- `arguments`: The function parameters
- `return_type`: The return type

**If no rows returned**: The function wasn't created. Re-run the migration SQL.

## Step 2: Refresh PostgREST Schema Cache

Supabase uses PostgREST to expose functions via RPC. After creating a new function, PostgREST's schema cache needs to be refreshed.

### Option A: Wait (Automatic Refresh)
PostgREST automatically refreshes its schema cache every few minutes. Wait 2-5 minutes and try again.

### Option B: Manual Refresh (Recommended)
1. Go to your Supabase Dashboard
2. Navigate to **Settings** → **API**
3. Look for **"Reload Schema"** or **"Refresh Schema Cache"** button
4. Click it to force a schema refresh

### Option C: Restart PostgREST (If available)
If you have access to Supabase CLI or infrastructure:
```bash
# This is usually handled automatically by Supabase
# But if you have direct access, you can restart the PostgREST service
```

## Step 3: Test the Function Directly

After refreshing, test the function directly in SQL:

```sql
-- Test the function (replace with actual values)
SELECT * FROM hybrid_search_sessions(
    query_text := 'test query',
    query_embedding := (SELECT embedding FROM sessions WHERE embedding IS NOT NULL LIMIT 1),
    filter_user_name := 'your_username',
    limit_count := 5
);
```

**Note**: This test requires at least one session with an embedding in your database.

## Step 4: Check for Errors in Migration

If the function doesn't exist, check for errors:

1. **Check if pgvector extension is enabled**:
```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```

If no rows, run:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

2. **Check if topics column exists**:
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'sessions' AND column_name = 'topics';
```

If no rows, run the topics migration first:
```sql
-- Run docs/migrations/add_topics_column.sql first
```

3. **Check for syntax errors**:
   - Make sure you copied the entire migration SQL
   - Check for any error messages in the Supabase SQL editor

## Common Issues

### Issue: "Function not found" even after creating it
**Solution**: Refresh PostgREST schema cache (Step 2)

### Issue: "Column 'topics' does not exist"
**Solution**: Run `docs/migrations/add_topics_column.sql` first

### Issue: "Type 'vector' does not exist"
**Solution**: Enable pgvector extension:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Issue: Function exists but RPC call fails
**Solution**: 
1. Verify function signature matches exactly
2. Check parameter names (Supabase RPC is case-sensitive)
3. Ensure all required parameters are provided

## Verification Query

Run this complete verification:

```sql
-- 1. Check if function exists
SELECT 
    'Function exists' AS status,
    p.proname AS function_name
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = 'public' 
  AND p.proname = 'hybrid_search_sessions';

-- 2. Check if required columns exist
SELECT 
    'Required columns' AS check_type,
    column_name,
    data_type
FROM information_schema.columns 
WHERE table_name = 'sessions' 
  AND column_name IN ('topics', 'embedding', 'summary', 'user_name');

-- 3. Check if pgvector extension exists
SELECT 
    'pgvector extension' AS check_type,
    extname AS extension_name
FROM pg_extension 
WHERE extname = 'vector';
```

All three queries should return results for everything to work correctly.

