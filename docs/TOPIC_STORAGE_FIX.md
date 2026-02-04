# Topic Storage Fix

## Issues Fixed

### 1. Topics Not Being Stored in Database ✅

**Problem**: Topics were being extracted but not saved to the database.

**Root Causes**:
- Topics could be `None` instead of empty list
- No error handling for missing database column
- Insufficient logging to debug issues

**Fixes Applied**:

1. **Ensure topics is always a list**:
   - Added checks in `summary_service.py` to convert `None` to `[]`
   - Added check in `database_service.py` to ensure topics is never `None`

2. **Better error handling**:
   - Added try-catch around database insert
   - Check for missing column error and provide helpful message
   - Log data keys being inserted for debugging

3. **Improved logging**:
   - Changed topic extraction log from DEBUG to INFO
   - Added warning when no topics extracted
   - Log topics being added to database

**Code Changes**:
```python
# summary_service.py - Always return a list
if topics is None:
    topics = []

# database_service.py - Always store array (even if empty)
if topics is None:
    topics = []
if topics:
    data["topics"] = topics
    logger.info(f"Adding {len(topics)} topics: {topics}")
else:
    data["topics"] = []  # Store empty array
```

### 2. Added "singing" to Topic Vocabulary ✅

**Problem**: User asked about "singing classes" but it wasn't in the topic vocabulary, so it wasn't extracted.

**Fix**: Added to `WELLNESS_TOPICS`:
- `'singing'`
- `'music'`
- `'vocal'`

**Impact**: Now "singing classes" will be extracted as `["singing"]` topic.

### 3. Better Error Messages ✅

**Added**:
- Clear error message if `topics` column doesn't exist in database
- Instructions to run migration script
- Logging of data keys being inserted

---

## Verification Steps

1. **Check if topics column exists**:
   ```sql
   SELECT column_name, data_type 
   FROM information_schema.columns 
   WHERE table_name = 'sessions' AND column_name = 'topics';
   ```

2. **If column doesn't exist, run migration**:
   ```sql
   ALTER TABLE sessions ADD COLUMN IF NOT EXISTS topics TEXT[];
   CREATE INDEX IF NOT EXISTS idx_sessions_topics_gin 
   ON sessions USING gin(topics);
   ```

3. **Check logs for topic extraction**:
   - Look for: `"Extracted X topics from user messages: [...]"`
   - Look for: `"Adding X topics to session data: [...]"`

4. **Check for errors**:
   - Look for: `"Topics column may not exist in database"`
   - Look for: `"Database insert error"`

---

## Expected Behavior

### Before Fix
- Topics extracted but not stored
- No error messages
- "singing" not recognized as topic

### After Fix
- Topics always stored (even if empty array)
- Clear error messages if column missing
- "singing" recognized and extracted
- Better logging for debugging

---

## Testing

1. **Test topic extraction**:
   - User message: "What did we discuss about singing classes?"
   - Expected topics: `["singing"]`
   - Check logs: Should see "Extracted 1 topics: ['singing']"

2. **Test database storage**:
   - After session ends, check logs for "Adding X topics to session data"
   - Query database: `SELECT topics FROM sessions WHERE user_name = 'wika' ORDER BY created_at DESC LIMIT 1;`
   - Should see topics array

3. **Test error handling**:
   - If column doesn't exist, should see clear error message with migration instructions

---

## Notes

- Topics are now always stored as an array (never `None`)
- Empty arrays are stored (better than `NULL` for queries)
- "singing" is now in vocabulary and will be extracted
- Better error messages help diagnose database issues

