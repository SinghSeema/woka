# Flow Verification Logging

## Overview

Added comprehensive logging to verify the complete flow:
**Embedding → Similarity Search → Find Matches → Extract Summary Text → Inject into Prompt**

---

## Logging Markers

All flow-related logs are prefixed with `[FLOW-STEP-X]` or `[FLOW-ENTRY]` or `[FLOW-COMPLETE]` for easy identification.

---

## Complete Flow with Logging

### Step 1: Fetch and Store Embeddings (Startup)

**Location**: `backend/bot/services/shadow_memory.py`

**Logs**:
```
📥 [FLOW-STEP-1] Fetching embeddings for {user_name}...
💾 [FLOW-STEP-1] Storing {N} embeddings in Shadow Memory (each has summary + embedding vector)
   Embedding 1: summary_len={X}, embedding_dim={Y}, preview='{summary_preview}...'
   ...
✅ [FLOW-STEP-1] Embeddings stored and ready for similarity search
```

**What to Verify**:
- ✅ Embeddings are fetched
- ✅ Each embedding has both `summary` and `embedding` fields
- ✅ Embeddings are stored in Shadow Memory

---

### Step 2: Generate Query Embedding

**Location**: `backend/bot/services/database_service.py` → `get_sessions_by_semantic_search()`

**Logs**:
```
🚀 [FLOW-ENTRY] Starting semantic search: user={user}, query='{query}...', limit={N}, threshold={X}
🔑 [FLOW-STEP-1] Generating query embedding for: '{query}...'
✅ [FLOW-STEP-1] Query embedding generated: dim={N}
```

**What to Verify**:
- ✅ Query embedding is generated
- ✅ Embedding dimension matches expected size

---

### Step 3: Similarity Search

**Location**: `backend/bot/services/database_service.py` → `search_cached_embeddings()`

**Logs**:
```
🔍 [FLOW-STEP-2] Checking Shadow Memory for cached embeddings...
✅ [FLOW-STEP-2] Found {N} cached embeddings, performing local similarity search...
🔍 [FLOW-STEP-2] Starting similarity search: query_embedding_dim={N}, cached_embeddings_count={M}, threshold={X}
   Item 1: similarity={X.XXX}, summary_len={N}, threshold={Y}, match={✅/❌}
   ...
📊 [FLOW-STEP-2] Similarity search complete: found {N} matches above threshold {X}
✅ [FLOW-STEP-2] Found {N} matches, extracting summary text...
   Match 1: similarity={X.XXX}, summary_len={N}, summary_preview='{preview}...'
   ...
```

**What to Verify**:
- ✅ Cached embeddings are found
- ✅ Similarity calculation is performed
- ✅ Matches are found above threshold
- ✅ Summary text is present in matches

---

### Step 4: Extract Summary Text

**Location**: `backend/bot/services/database_service.py` → `search_cached_embeddings()`

**Logs**:
```
📝 [FLOW-STEP-3] Extracting summary text from {N} matches...
   Extracting summary: len={N}, preview='{preview}...'
   ...
✅ [FLOW-STEP-3] Extracted {N} summary texts ready for prompt injection
   Result 1: summary_len={N}, similarity={X.XXX}
   ...
```

**What to Verify**:
- ✅ Summary text is extracted from matches
- ✅ Summary text has content (len > 0)
- ✅ Results contain summary text

---

### Step 5: Return Sessions with Summary Text

**Location**: `backend/bot/services/database_service.py` → `get_sessions_by_semantic_search()`

**Logs**:
```
📋 [FLOW-STEP-3] Returning {N} sessions with summary text ready for prompt injection
   Session 1: similarity={X.XXX}, summary_len={N}, has_summary_text={✅/❌}
   ...
```

**What to Verify**:
- ✅ Sessions are returned
- ✅ Each session has `summary` field
- ✅ Summary text is present (has_summary_text=✅)

---

### Step 6: Pass to Injection

**Location**: `backend/bot/services/past_context_processor.py`

**Logs**:
```
📤 [FLOW-STEP-4] Passing {N} sessions to inject_past_context for prompt injection...
   Session 1 before injection: has_summary={✅/❌}, summary_len={N}
   ...
```

**What to Verify**:
- ✅ Sessions are passed to injection function
- ✅ Each session has summary text before injection

---

### Step 7: Format and Inject Summary Text

**Location**: `backend/bot/services/context_injector.py` → `inject_past_context()`

**Logs**:
```
💉 [FLOW-STEP-4] Starting prompt injection: sessions={N}, user={user}, query='{query}...'
   Session 1 for injection: has_summary={✅/❌}, summary_len={N}, similarity={X.XXX}
   ...
📝 [FLOW-STEP-4] Formatting {N} sessions into context text...
✅ [FLOW-STEP-4] Context text formatted: len={N} chars
✅ [FLOW-STEP-4] Injected summary text into system prompt: original_size={N}, new_size={M}, injected_size={K} chars
🎯 [FLOW-COMPLETE] Summary text successfully injected into prompt! Flow: Embedding → Similarity Search → Matches → Summary Text → Prompt ✅
```

**What to Verify**:
- ✅ Sessions have summary text
- ✅ Context text is formatted
- ✅ Summary text is injected into system prompt
- ✅ Flow completes successfully

---

## Fallback Path (Supabase Query)

If local cache doesn't have embeddings, logs show fallback:

```
ℹ️  [FLOW-STEP-2] No cached embeddings in Shadow Memory, will try Supabase
🌐 [FLOW-STEP-2-FALLBACK] Falling back to Supabase vector search...
🔍 [FLOW-STEP-2-FALLBACK] Querying Supabase with vector similarity search...
✅ [FLOW-STEP-2-FALLBACK] Supabase search found {N} relevant sessions...
📋 [FLOW-STEP-3] Extracting summary text from {N} Supabase results...
```

---

## How to Verify the Flow

### 1. Check Startup Logs

Look for:
```
📥 [FLOW-STEP-1] Fetching embeddings...
💾 [FLOW-STEP-1] Storing {N} embeddings...
✅ [FLOW-STEP-1] Embeddings stored and ready
```

**Expected**: Embeddings are fetched and stored with both summary and embedding.

---

### 2. Check Query Logs

When user asks about past, look for:
```
🚀 [FLOW-ENTRY] Starting semantic search...
🔑 [FLOW-STEP-1] Generating query embedding...
✅ [FLOW-STEP-1] Query embedding generated
```

**Expected**: Query embedding is generated.

---

### 3. Check Similarity Search Logs

Look for:
```
🔍 [FLOW-STEP-2] Starting similarity search...
   Item 1: similarity={X}, match={✅/❌}
📊 [FLOW-STEP-2] Similarity search complete: found {N} matches
```

**Expected**: Similarity is calculated and matches are found.

---

### 4. Check Summary Extraction Logs

Look for:
```
📝 [FLOW-STEP-3] Extracting summary text...
✅ [FLOW-STEP-3] Extracted {N} summary texts ready for prompt injection
   Result 1: summary_len={N}, has_summary_text={✅}
```

**Expected**: Summary text is extracted from matches.

---

### 5. Check Injection Logs

Look for:
```
💉 [FLOW-STEP-4] Starting prompt injection...
   Session 1: has_summary={✅}, summary_len={N}
✅ [FLOW-STEP-4] Injected summary text into system prompt
🎯 [FLOW-COMPLETE] Summary text successfully injected into prompt! ✅
```

**Expected**: Summary text is injected into prompt.

---

## Troubleshooting

### Problem: No embeddings stored

**Look for**:
```
⚠️  [FLOW-STEP-1] No embeddings found for {user}
```

**Solution**: Check if user has past sessions in Supabase.

---

### Problem: No matches found

**Look for**:
```
⚠️  [FLOW-STEP-2] No matches found above threshold {X}
```

**Solution**: 
- Check threshold value (might be too high)
- Check if embeddings are similar enough
- Check if cached embeddings exist

---

### Problem: No summary text

**Look for**:
```
   Session 1: has_summary={❌}, summary_len={0}
⚠️  Session 1 has NO summary text - cannot inject!
```

**Solution**: Check if embeddings were stored with summary text.

---

### Problem: Injection failed

**Look for**:
```
⚠️  [FLOW-STEP-4] inject_past_context returned success=False
```

**Solution**: Check context injection logic.

---

## Summary

All logging is now in place to verify the complete flow:

1. ✅ **Embedding** - Fetched and stored (with summary)
2. ✅ **Similarity Search** - Performed using embeddings
3. ✅ **Find Matches** - Matches found above threshold
4. ✅ **Extract Summary Text** - Summary text extracted from matches
5. ✅ **Inject into Prompt** - Summary text injected into system prompt

**Look for `[FLOW-STEP-X]` markers in logs to trace the complete flow!**

