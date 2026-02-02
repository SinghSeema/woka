# Code Flow: Getting Summary Text from Embeddings

## Answer: We Store BOTH Summary + Embedding

**Key Point**: Embeddings are ONE-WAY. We CANNOT reconstruct text from embeddings.
**Solution**: Store summary text ALONG WITH embeddings.

---

## Complete Code Flow

### Step 1: Fetch and Store (Both Summary + Embedding)

**Location**: `backend/bot/services/database_service.py`

```python
async def get_past_session_embeddings(user_name: str, limit: int = 3):
    """Fetch summary AND embedding (both needed!)."""
    
    result = (
        client.table("sessions")
        .select("summary, embedding")  # ← BOTH!
        .eq("user_name", normalized_name)
        .not_.is_("embedding", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    
    # Returns: [{"summary": "...", "embedding": [...]}, ...]
    return result.data
```

**What We Get**:
```python
[
    {
        "summary": "We discussed sleep schedule and aiming for 8 hours...",  # ← Text
        "embedding": [0.1, 0.2, 0.3, ...]  # ← Vector
    },
    ...
]
```

---

### Step 2: Store in Shadow Memory (Both)

**Location**: `backend/bot/services/shadow_memory.py`

```python
async def prewarm(self, limit: int = 5):
    # Fetch embeddings (summary + embedding)
    embedding_data = await get_past_session_embeddings(self.user_name, limit=limit)
    
    # Store BOTH in Shadow Memory
    self.cached_embeddings = embedding_data  # ← Contains both!
    
    # Also store in embedding cache
    await self._prewarm_embedding_cache(embedding_data)
```

**What We Store**:
```python
self.cached_embeddings = [
    {
        "summary": "We discussed sleep...",  # ← For prompt injection
        "embedding": [0.1, 0.2, ...]         # ← For similarity search
    }
]
```

---

### Step 3: Search Using Embeddings (Find Matches)

**Location**: `backend/bot/services/database_service.py`

```python
async def search_cached_embeddings(
    query_embedding: List[float],
    cached_embeddings: List[Dict[str, Any]],  # ← Contains both summary + embedding
    threshold: float = 0.7,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Search using embeddings, return matches with summary text."""
    
    matches = []
    for item in cached_embeddings:
        summary = item.get("summary", "")      # ← Extract summary text
        embedding = item.get("embedding")      # ← Extract embedding vector
        
        # Use EMBEDDING for similarity search
        similarity = cosine_similarity(query_embedding, embedding)
        
        if similarity >= threshold:
            # Store BOTH summary text AND similarity score
            matches.append({
                "summary": summary,            # ← Keep summary text!
                "similarity": similarity,
                "embedding": embedding
            })
    
    # Sort by similarity
    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:limit]
```

**What We Return**:
```python
[
    {
        "summary": "We discussed sleep schedule...",  # ← Summary text (for prompt!)
        "similarity": 0.92,                           # ← How relevant
        "embedding": [...]                            # ← Can discard after search
    }
]
```

---

### Step 4: Extract Summary Text from Matches

**Location**: `backend/bot/services/past_context_processor.py`

```python
async def _handle_fetch(self, user_message: str) -> bool:
    # ... detect intent ...
    
    # Search using embeddings
    sessions = await get_sessions_by_semantic_search(
        self._user_name,
        query_text,
        shadow_memory=self._shadow_memory
    )
    
    # Sessions now contain summary text!
    # sessions = [
    #     {
    #         "summary": "We discussed sleep...",  # ← This is what we need!
    #         "similarity": 0.92,
    #         ...
    #     }
    # ]
    
    # Inject summary text into prompt
    if sessions:
        inject_past_context(self._context, sessions, self._user_name, query_text)
```

---

### Step 5: Inject Summary Text into Prompt

**Location**: `backend/bot/services/context_injector.py`

```python
def inject_past_context(
    context: "OpenAILLMContext",
    sessions: List[Dict[str, Any]],  # ← Contains summary text
    user_name: str,
    query_text: Optional[str] = None
) -> bool:
    """Inject summary TEXT into LLM context."""
    
    # Format sessions into context string
    context_text = _format_sessions_for_injection(sessions, user_name, query_text)
    
    # Inject into system prompt
    messages = context.get_messages()
    for msg in messages:
        if msg.get("role") == "system":
            # Append summary TEXT to system prompt
            msg["content"] += "\n\n" + context_text
            break
```

**What Gets Injected**:
```python
def _format_sessions_for_injection(sessions, user_name, query_text):
    """Format summary TEXT for injection."""
    
    for session in sessions:
        summary = session.get("summary", "")  # ← Extract summary TEXT
        # ... format ...
        context_parts.append(f"Summary: {summary}\n\n")  # ← Inject TEXT
    
    return "".join(context_parts)
```

**Result**:
```
## ADDITIONAL CONTEXT
Session 1 - January 15, 2024
Summary: We discussed sleep schedule and aiming for 8 hours...
```

---

## Complete Flow Diagram

```
1. Fetch from Supabase
   ↓
   {"summary": "...", "embedding": [...]}
   ↓
2. Store in Shadow Memory
   ↓
   cached_embeddings = [{"summary": "...", "embedding": [...]}]
   ↓
3. User Query: "What did we discuss about sleep?"
   ↓
4. Generate Query Embedding
   ↓
   query_embedding = [0.1, 0.2, ...]
   ↓
5. Search Using Embeddings (similarity)
   ↓
   for item in cached_embeddings:
       similarity = cosine_similarity(query_embedding, item["embedding"])
       if similarity > threshold:
           matches.append({
               "summary": item["summary"],  # ← Extract TEXT
               "similarity": similarity
           })
   ↓
6. Extract Summary Text
   ↓
   summary_text = matches[0]["summary"]  # ← "We discussed sleep..."
   ↓
7. Inject Summary Text into Prompt
   ↓
   context_text = f"## PAST SESSION\n{summary_text}\n"
   inject_past_context(context, [{"summary": summary_text}])
   ↓
8. LLM Receives Summary Text
   ↓
   "## ADDITIONAL CONTEXT
    Session 1
    Summary: We discussed sleep schedule and aiming for 8 hours..."
```

---

## Key Code Locations

### 1. Fetch Both (Summary + Embedding)
**File**: `backend/bot/services/database_service.py`
**Function**: `get_past_session_embeddings()`
**Line**: ~247

```python
.select("summary, embedding")  # ← Both!
```

### 2. Store Both
**File**: `backend/bot/services/shadow_memory.py`
**Function**: `prewarm()`
**Line**: ~73

```python
self.cached_embeddings = embedding_data  # ← Contains both
```

### 3. Search Using Embedding, Extract Summary
**File**: `backend/bot/services/database_service.py`
**Function**: `search_cached_embeddings()`
**Line**: ~143

```python
summary = item.get("summary", "")      # ← Extract text
embedding = item.get("embedding")      # ← Extract vector
similarity = cosine_similarity(query_embedding, embedding)  # ← Use embedding
matches.append({"summary": summary, ...})  # ← Keep text!
```

### 4. Inject Summary Text
**File**: `backend/bot/services/context_injector.py`
**Function**: `_format_sessions_for_injection()`
**Line**: ~155

```python
summary = session.get("summary", "")  # ← Get text
context_parts.append(f"Summary: {summary}\n\n")  # ← Inject text
```

---

## Summary

### Question: "How do we get summary text from embeddings?"

**Answer**: We DON'T get text from embeddings. We store text ALONG WITH embeddings.

### Question: "Should we store summary WITH embeddings or only embeddings?"

**Answer**: Store BOTH. They serve different purposes:
- **Embedding**: For similarity search (find relevant sessions)
- **Summary Text**: For prompt injection (feed to LLM)

### Current Implementation: ✅ CORRECT

We already do this correctly:
1. ✅ Fetch both summary + embedding
2. ✅ Store both in Shadow Memory
3. ✅ Use embedding for similarity search
4. ✅ Extract summary text from matches
5. ✅ Inject summary text into prompt

**No changes needed - the architecture is correct!**

