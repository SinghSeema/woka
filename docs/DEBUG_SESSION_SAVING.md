# Debugging Session Summary Saving

If session summaries are not being saved to Supabase, follow this debugging guide.

## Checklist

### 1. Verify Supabase Configuration

Check your `.env` file has:
```bash
SUPABASE_ENABLED=true
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

**Verify**: Check bot logs on startup - you should see:
- `Supabase client initialized` (if enabled and configured correctly)
- `Supabase enabled but URL or KEY not configured` (if misconfigured)

### 2. Check Session Requirements

Summaries are only saved if:
- ✅ Session duration ≥ 30 seconds
- ✅ At least 2 messages exchanged (user + assistant)
- ✅ Supabase is enabled
- ✅ Session doesn't already exist (by room_name)

### 3. Check Bot Logs

When a session ends, look for these log messages:

**On session end:**
```
Attempting to save session summary for [user] (room: [room_name])
Session duration: X.X seconds
Found X messages in context
```

**If requirements not met:**
```
Session too short to save: X.Xs (minimum 30s required)
OR
Not enough messages to save: X (minimum 2 required)
```

**If saving:**
```
Generating summary for X messages, duration: X.Xs
Generated summary (X chars): ...
✅ Successfully saved session summary for [user] (room: [room_name])
```

**If errors:**
```
❌ Supabase disabled in settings
❌ Supabase client not available
❌ Error saving session summary to Supabase: [error details]
```

### 4. Common Issues

#### Issue: "Supabase disabled, skipping session save"
**Solution**: Set `SUPABASE_ENABLED=true` in `.env`

#### Issue: "Supabase client not available"
**Solution**: 
- Check `SUPABASE_URL` and `SUPABASE_KEY` in `.env`
- Verify the Supabase project is active
- Check network connectivity

#### Issue: "Session too short to save"
**Solution**: 
- Have a conversation longer than 30 seconds
- Ensure at least 2 messages are exchanged

#### Issue: "Not enough messages to save"
**Solution**: 
- Make sure you're having a conversation (not just listening)
- Bot needs to respond at least once
- Check if `context.get_messages()` is returning messages

#### Issue: "Session already saved, skipping"
**Solution**: 
- This is normal - prevents duplicate saves
- Each room_name can only be saved once

#### Issue: "Error saving session summary to Supabase"
**Solution**:
- Check the error message in logs
- Verify table `sessions` exists in Supabase
- Check RLS policies allow inserts
- Verify column names match schema

### 5. Manual Testing

To test if saving works:

1. **Start a session** and have a conversation:
   - Talk for at least 30 seconds
   - Exchange at least 2 messages (you speak, bot responds)

2. **Disconnect** from the session

3. **Check bot logs** for the save attempt

4. **Check Supabase**:
   ```sql
   SELECT * FROM sessions 
   ORDER BY created_at DESC 
   LIMIT 5;
   ```

### 6. Verify Database Connection

Test Supabase connection:
```python
# In Python shell or test script
from bot.services.database_service import get_supabase_client
client = get_supabase_client()
if client:
    print("✅ Supabase client connected")
    # Test query
    result = client.table("sessions").select("*").limit(1).execute()
    print(f"✅ Query successful: {len(result.data)} rows")
else:
    print("❌ Supabase client not available")
```

### 7. Check Table Schema

Verify your `sessions` table matches:
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'sessions';
```

Expected columns:
- `id` (UUID)
- `room_name` (TEXT)
- `user_name` (TEXT)
- `summary` (TEXT)
- `duration_seconds` (INTEGER)
- `message_count` (INTEGER)
- `created_at` (TIMESTAMPTZ)
- `updated_at` (TIMESTAMPTZ)

### 8. Enable Debug Logging

To see more details, ensure logging level is INFO or DEBUG:
```python
# In app/core/logging.py or .env
LOG_LEVEL=INFO  # or DEBUG for more details
```

## Quick Test

Run this to test the save function directly:

```python
import asyncio
from bot.services.database_service import save_session_summary

async def test():
    result = await save_session_summary(
        user_name="TestUser",
        room_name="test-room-123",
        summary="This is a test summary to verify the database connection works correctly.",
        duration_seconds=60,
        message_count=5
    )
    print(f"Save result: {result}")

asyncio.run(test())
```

If this works, the issue is likely in the event handlers or message extraction.

