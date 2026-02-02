# Dynamic Query Troubleshooting Guide

## Problem

Only startup steps are happening (FLOW-STEP-1 for fetching embeddings), but dynamic queries and summary fetching are NOT happening when user asks about past sessions.

---

## What to Check in Logs

### 1. Check if PastContextProcessor is Initialized

**Look for**:
```
🔧 [DYNAMIC-QUERY] PastContextProcessor initialized: 
   user={user}, room={room}, 
   ENABLE_DYNAMIC_CONTEXT={True/False}, 
   ENABLE_SEMANTIC_SEARCH={True/False}, 
   has_context_cache={True/False}, 
   has_shadow_memory={True/False}
```

**Expected**: 
- ✅ `ENABLE_DYNAMIC_CONTEXT=True`
- ✅ `ENABLE_SEMANTIC_SEARCH=True`
- ✅ `has_shadow_memory=True`

**If `ENABLE_DYNAMIC_CONTEXT=False`**: 
- Set `ENABLE_DYNAMIC_CONTEXT=true` in your `.env` file

---

### 2. Check if process_frame is Being Called

**Look for**:
```
🔍 [DYNAMIC-QUERY] PastContextProcessor.process_frame: 
   frame_type={FrameType}, direction={UPSTREAM/DOWNSTREAM}
```

**Expected**: Should see this for every frame that passes through.

**If NOT seeing this**: 
- PastContextProcessor might not be in the pipeline
- Check `main.py` to ensure it's added to pipeline

---

### 3. Check if LLMContextFrame is Received

**Look for**:
```
✅ [DYNAMIC-QUERY] Received LLMContextFrame (DOWNSTREAM) - checking for user message...
```

**Expected**: Should see this when user sends a message.

**If NOT seeing this**:
- Frames might not be LLMContextFrame type
- Check if frames are going in DOWNSTREAM direction

---

### 4. Check if User Message is Found

**Look for**:
```
👤 [DYNAMIC-QUERY] Found user message: '{message}...' (len={N})
```

**Expected**: Should see the user's message text.

**If NOT seeing this**:
- No user message in context
- Check if messages are being added to context correctly

---

### 5. Check ENABLE_DYNAMIC_CONTEXT Setting

**Look for**:
```
⚠️  [DYNAMIC-QUERY] ENABLE_DYNAMIC_CONTEXT is DISABLED - skipping past context fetch
```

**OR**:
```
✅ [DYNAMIC-QUERY] ENABLE_DYNAMIC_CONTEXT is enabled - processing user message...
```

**Expected**: Should see "enabled" message.

**If seeing "DISABLED"**:
- Set `ENABLE_DYNAMIC_CONTEXT=true` in `.env` file
- Restart the bot

---

### 6. Check Intent Detection

**Look for**:
```
🎯 [DYNAMIC-QUERY] Detecting past-reference intent...
   Intent detection result: has_intent={True/False}, 
   intent_type={type}, query_text={text}...
```

**Expected**: 
- `has_intent=True` for past-reference queries
- `intent_type` should be one of: 'general', 'date', 'topic', 'semantic'

**If `has_intent=False`**:
- User message might not contain past-reference keywords
- Check `intent_detector.py` for keywords
- Try queries like:
  - "What did we discuss last session?"
  - "Tell me about our past conversations"
  - "What did we talk about before?"

---

### 7. Check if Context Fetch is Triggered

**Look for**:
```
✅ [DYNAMIC-QUERY] Detected intent '{type}' - proceeding with context fetch
🚀 [FLOW-ENTRY] Starting semantic search...
```

**Expected**: Should see these after intent is detected.

**If NOT seeing this**:
- Intent detection is failing
- Check step 6 above

---

## Common Issues and Solutions

### Issue 1: ENABLE_DYNAMIC_CONTEXT is False

**Symptoms**:
```
⚠️  [DYNAMIC-QUERY] ENABLE_DYNAMIC_CONTEXT is DISABLED
```

**Solution**:
1. Check `.env` file:
   ```bash
   ENABLE_DYNAMIC_CONTEXT=true
   ```
2. Restart the bot

---

### Issue 2: Intent Detection Not Working

**Symptoms**:
```
Intent detection result: has_intent=False
```

**Solution**:
1. Try queries with explicit past-reference keywords:
   - "What did we discuss?"
   - "Tell me about our last session"
   - "What did we talk about before?"
2. Check `intent_detector.py` for supported keywords
3. Add more keywords if needed

---

### Issue 3: PastContextProcessor Not in Pipeline

**Symptoms**:
- No `[DYNAMIC-QUERY]` logs at all

**Solution**:
1. Check `main.py` line ~199:
   ```python
   past_context_handler = PastContextProcessor(...)
   ```
2. Check `main.py` line ~223:
   ```python
   pipeline_components = [
       ...,
       past_context_handler,  # ← Should be here
       ...
   ]
   ```

---

### Issue 4: No LLMContextFrame Received

**Symptoms**:
```
⏭️  [DYNAMIC-QUERY] Skipping frame: not LLMContextFrame
```

**Solution**:
- This might be normal for some frames
- Check if you see `✅ [DYNAMIC-QUERY] Received LLMContextFrame` when user sends message

---

### Issue 5: No User Message in Context

**Symptoms**:
```
⚠️  [DYNAMIC-QUERY] No user message found in context
```

**Solution**:
- Check if messages are being added to context correctly
- Check if message role is "user"
- Check if message content is not empty

---

## Test Queries

Try these queries to trigger dynamic context:

1. **General past reference**:
   - "What did we discuss last session?"
   - "Tell me about our past conversations"
   - "What did we talk about before?"

2. **Date-specific**:
   - "What did we discuss yesterday?"
   - "Tell me about last week's session"

3. **Topic-specific**:
   - "What did we discuss about sleep?"
   - "Tell me about our conversation regarding exercise"

---

## Expected Log Flow

When working correctly, you should see:

```
🔧 [DYNAMIC-QUERY] PastContextProcessor initialized: ENABLE_DYNAMIC_CONTEXT=True
🔍 [DYNAMIC-QUERY] PastContextProcessor.process_frame: frame_type=LLMContextFrame, direction=DOWNSTREAM
✅ [DYNAMIC-QUERY] Received LLMContextFrame (DOWNSTREAM) - checking for user message...
👤 [DYNAMIC-QUERY] Found user message: 'What did we discuss...' (len=25)
✅ [DYNAMIC-QUERY] ENABLE_DYNAMIC_CONTEXT is enabled - processing user message...
🔍 [DYNAMIC-QUERY] _handle_fetch called for message: 'What did we discuss...'
🎯 [DYNAMIC-QUERY] Detecting past-reference intent...
   Intent detection result: has_intent=True, intent_type=general, query_text=What did we discuss...
✅ [DYNAMIC-QUERY] Detected intent 'general' - proceeding with context fetch
🚀 [FLOW-ENTRY] Starting semantic search...
🔑 [FLOW-STEP-1] Generating query embedding...
🔍 [FLOW-STEP-2] Starting similarity search...
📊 [FLOW-STEP-2] Similarity search complete: found 2 matches
📝 [FLOW-STEP-3] Extracting summary text...
💉 [FLOW-STEP-4] Starting prompt injection...
✅ [FLOW-STEP-4] Injected summary text into system prompt
🎯 [FLOW-COMPLETE] Summary text successfully injected into prompt! ✅
```

---

## Next Steps

1. **Check logs** for the markers above
2. **Identify which step is failing**
3. **Apply the solution** from the troubleshooting guide
4. **Test again** with a past-reference query

The comprehensive logging will show exactly where the flow is breaking!

