# Supabase Free Tier - Functions Support

## ✅ Yes, Functions Are Supported!

Supabase **Free Tier fully supports PostgreSQL functions**. All PostgreSQL features work on the free tier, including:

- ✅ Custom functions (stored procedures)
- ✅ RPC calls via PostgREST API
- ✅ Extensions (pgvector, etc.)
- ✅ Triggers, views, and all PostgreSQL features

## Free Tier Limitations

The free tier limits are about **resources**, not **features**:

| Resource | Free Tier Limit |
|----------|----------------|
| Database Size | 500 MB |
| Bandwidth | 2 GB/month |
| API Requests | 50,000/month |
| File Storage | 1 GB |
| **PostgreSQL Functions** | ✅ **Unlimited** |

## Common Issues with Functions on Free Tier

### 1. Schema Cache Refresh (Most Common)

**Problem**: Function exists but PostgREST can't see it  
**Cause**: PostgREST schema cache needs refresh  
**Solution**: 
- Wait 2-5 minutes (auto-refresh)
- Or manually refresh in Dashboard → Settings → API

### 2. Function Not Created

**Problem**: Migration ran but function doesn't exist  
**Causes**:
- Syntax error in SQL
- Missing dependencies (extensions, columns)
- Error message was ignored

**Solution**: Check for errors in SQL Editor output

### 3. RPC Call Fails

**Problem**: Function exists but RPC call returns error  
**Causes**:
- Parameter name mismatch (PostgREST is case-sensitive)
- Missing required parameters
- Type mismatch

**Solution**: Verify function signature matches exactly

## Verification Steps for Free Tier

### Step 1: Verify Function Exists

```sql
-- Run in Supabase SQL Editor
SELECT 
    p.proname AS function_name,
    pg_get_function_arguments(p.oid) AS arguments
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = 'public' 
  AND p.proname = 'hybrid_search_sessions';
```

**Expected**: One row with function details  
**If empty**: Function wasn't created - check for errors

### Step 2: Check Dependencies

```sql
-- Check if pgvector extension exists
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Check if topics column exists
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'sessions' AND column_name = 'topics';
```

### Step 3: Test Function Directly

```sql
-- Test the function (adjust values as needed)
SELECT * FROM hybrid_search_sessions(
    query_text := 'test',
    query_embedding := (SELECT embedding FROM sessions WHERE embedding IS NOT NULL LIMIT 1),
    filter_user_name := 'test_user',
    limit_count := 1
);
```

**Note**: This requires at least one session with an embedding.

### Step 4: Refresh PostgREST Cache

1. Go to Supabase Dashboard
2. Navigate to **Settings** → **API**
3. Look for **"Reload Schema"** or similar button
4. Click to refresh schema cache

**Alternative**: Wait 2-5 minutes for automatic refresh

## Why Your Function Might Not Work

### If you see "function not found" error:

1. **Function doesn't exist** → Re-run migration, check for errors
2. **Schema cache not refreshed** → Wait or manually refresh
3. **Wrong schema** → Ensure function is in `public` schema
4. **Permissions** → Free tier should have full permissions by default

### If function exists but RPC fails:

1. **Parameter mismatch** → Check parameter names match exactly
2. **Type mismatch** → Verify vector dimension (384)
3. **Missing data** → Ensure sessions table has data with embeddings

## Free Tier Best Practices

1. **Test functions in SQL Editor first** before using in code
2. **Check error messages** in SQL Editor output
3. **Wait for schema refresh** after creating functions
4. **Use fallback logic** in code (already implemented)

## Your Current Setup

Your code already has a **fallback mechanism** that will:
- Try `hybrid_search_sessions` first
- Fall back to `match_sessions` if function not found
- Log a warning with instructions

This means your application will work even if:
- Function hasn't been created yet
- Schema cache hasn't refreshed
- There's a temporary issue

## Next Steps

1. **Verify function exists** using Step 1 query above
2. **If function exists**: Wait 2-5 minutes or refresh schema cache
3. **If function doesn't exist**: 
   - Check SQL Editor for error messages
   - Ensure `topics` column exists (run `add_topics_column.sql` first)
   - Ensure `vector` extension is enabled
   - Re-run migration

## Support

If you're still having issues:
- Check Supabase Dashboard → Logs for errors
- Verify all migrations ran successfully
- Test function directly in SQL Editor
- Check PostgREST logs in Dashboard

The free tier supports all PostgreSQL features - the issue is likely schema cache or migration execution, not tier limitations.

