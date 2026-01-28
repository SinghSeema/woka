# Context Injection Debug Guide

## Problem

Past context is not appearing in LLM prompts, even when:
1. Shadow Memory pre-warms sessions
2. User explicitly asks about past sessions
3. Intent detection should trigger

## Root Cause Analysis

### Issue 1: Message List Modification May Not Persist

`OpenAILLMContext.get_messages()` might return a **copy** or **view** of messages, not a direct reference. Modifying the returned list might not update the actual context used by the LLM.

**Current Pattern**:
```python
messages = context.get_messages()
messages[i]["content"] = updated_content  # Might not persist!
```

**Fixed Pattern** (like `remove_old_messages`):
```python
messages = context.get_messages()
messages[:] = new_messages  # Replace entire list
```

### Issue 2: Intent Detection May Not Match

User message: "Can you please tell me what we have discussed in the past sessions?"

**Keywords to check**:
- ✅ "past sessions" - matches
- ✅ "what we have discussed" - matches (added)
- ✅ "what we discussed" - matches

**Variations to handle**:
- "what we have discussed" vs "what we discussed"
- "past sessions" vs "past session"

### Issue 3: Monitoring May Not Be Running

The `monitor_messages()` function runs every 500ms, but:
- Might not catch messages in time
- Might have errors that are silently caught
- Might not be calling `handle_past_reference_query`

## Fixes Applied

### 1. Fixed Shadow Memory Injection Pattern

**File**: `backend/bot/services/shadow_memory.py`

**Before**:
```python
messages[i]["content"] = updated_content  # Direct modification
```

**After**:
```python
updated_messages = []
for msg in messages:
    if msg.get("role") == "system" and not injected:
        updated_messages.append({"role": "system", "content": updated_content})
        injected = True
    else:
        updated_messages.append(msg)
messages[:] = updated_messages  # Replace entire list
```

### 2. Enhanced Intent Detection

**File**: `backend/bot/services/intent_detector.py`

**Added keywords**:
- "past sessions"
- "past conversations"
- "what we discussed"
- "what we have discussed"
- "what we talked about"

**Added variations check**:
- "what we have"
- "what we've"
- "discussed in the past"
- "past session"

### 3. Added Debug Logging

**Files**: `backend/bot/handlers/events.py`, `backend/bot/services/intent_detector.py`

**Logs added**:
- Message detection: "🔍 New user message detected"
- Intent check: "Checking for past reference intent"
- Keyword detection: "✅ Past reference keyword detected"
- Intent result: "Detected past reference intent"
- Injection result: "✅ Past context injected"

## Testing Steps

1. **Check logs for Shadow Memory pre-warming**:
   ```
   🔥 Pre-warming Shadow Memory...
   ✅ Shadow Memory pre-warmed: X sessions cached
   ✅ Injected X pre-warmed sessions into initial system prompt
   ```

2. **Check logs for intent detection**:
   ```
   🔍 New user message detected: Can you please tell me...
   ✅ Past reference keyword detected
   🔍 Detected past reference intent: general (confidence: 0.8)
   ```

3. **Check logs for context injection**:
   ```
   ✅ Cache hit for query: type:general|query:...
   💉 Injecting X sessions into context
   ✅ Injected X sessions into context (X tokens, X chars)
   ```

4. **Verify context in LLM calls**:
   Check the debug log showing the actual context sent to LLM:
   ```
   GroqLLMService#0: Generating chat from LLM-specific context
   [{'role': 'system', 'content': '...PAST SESSIONS CONTEXT...'}]
   ```

## If Still Not Working

### Check Configuration

```python
# In .env or config
ENABLE_DYNAMIC_CONTEXT=True
INTENT_DETECTION_ENABLED=True
SUPABASE_ENABLED=True
```

### Check OpenAILLMContext Implementation

The issue might be that `OpenAILLMContext` uses internal storage that doesn't reflect `get_messages()` modifications. If `messages[:] = [...]` doesn't work, we might need to:

1. **Check Pipecat source** to see how `OpenAILLMContext` stores messages
2. **Use a different injection method** if available
3. **Recreate context** with updated messages (if possible)

### Alternative: Use LLMMessagesFrame

Instead of modifying context directly, we could inject via frames:
```python
await task.queue_frames([
    LLMMessagesFrame([{
        "role": "system",
        "content": past_context
    }])
])
```

But this might not work for system messages mid-conversation.

## Next Steps

1. Test with enhanced logging
2. Check logs for Shadow Memory completion
3. Check logs for intent detection
4. Verify context actually contains past sessions
5. If still failing, investigate OpenAILLMContext internals

