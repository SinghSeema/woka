# Where to Find Functions in Supabase Dashboard

## Functions Don't Appear in Tables Section

PostgreSQL functions are **not tables**, so they won't show up in the "Tables" section of your Supabase dashboard. They're stored in the database's function catalog.

## Where to See Functions in Supabase

### Option 1: SQL Editor (Recommended)

1. Go to **SQL Editor** in your Supabase Dashboard
2. Run this query to see all your functions:

```sql
SELECT 
    p.proname AS function_name,
    pg_get_function_arguments(p.oid) AS arguments,
    pg_get_function_result(p.oid) AS return_type
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = 'public'
ORDER BY p.proname;
```

This will show you all functions in the `public` schema, including `hybrid_search_sessions`.

### Option 2: Database Functions Section (If Available)

Some Supabase dashboard versions have a **"Functions"** or **"Database Functions"** section:
- Look in the left sidebar
- May be under **Database** → **Functions**
- Or **Database** → **Stored Procedures**

**Note**: This section may not exist in all Supabase dashboard versions. If you don't see it, use Option 1.

### Option 3: API Section (For RPC Calls)

1. Go to **Settings** → **API**
2. Look for **"RPC Functions"** or **"Database Functions"**
3. This shows functions that can be called via the API

## Your Function Exists - Next Step

Since you confirmed the function exists (Step 1 showed the function name), the issue is likely:

### Schema Cache Not Refreshed

PostgREST (Supabase's API layer) needs to refresh its schema cache to see new functions. Here's how to fix it:

#### Method 1: Wait (Easiest)
- Wait **2-5 minutes** after creating the function
- PostgREST automatically refreshes its cache periodically
- Try your application again

#### Method 2: Manual Refresh
1. Go to **Settings** → **API** in Supabase Dashboard
2. Look for a button like:
   - "Reload Schema"
   - "Refresh Schema Cache"
   - "Reload PostgREST Schema"
3. Click it to force a refresh

#### Method 3: Test Function Directly
Test if the function works in SQL Editor:

```sql
-- Test the function (replace with your actual data)
SELECT * FROM hybrid_search_sessions(
    query_text := 'test query',
    query_embedding := (
        SELECT embedding 
        FROM sessions 
        WHERE embedding IS NOT NULL 
        LIMIT 1
    ),
    filter_user_name := 'wika',  -- Replace with your username
    limit_count := 5
);
```

**If this works**: The function is fine, just wait for schema cache refresh  
**If this fails**: Check the error message for clues

## Verify Function is Callable via RPC

After schema cache refreshes, you can verify it's accessible via API:

1. Go to **Settings** → **API**
2. Look for **"RPC Functions"** section
3. You should see `hybrid_search_sessions` listed

## Summary

- ✅ **Function exists** (you confirmed this)
- ✅ **Table exists** (you confirmed this)
- ⏳ **Waiting for schema cache refresh** (this is the issue)

**Action**: Wait 2-5 minutes, then test your application again. The error should disappear once PostgREST refreshes its schema cache.

## Quick Test

After waiting, check your application logs. You should see:
- ✅ `[HYBRID SEARCH] Found X sessions` (success)
- Instead of: ⚠️ `Function 'hybrid_search_sessions' not found` (fallback)

If you still see the fallback message after 5 minutes, try the manual refresh method.

