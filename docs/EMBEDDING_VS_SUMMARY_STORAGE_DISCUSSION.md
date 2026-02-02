# Embedding vs Summary Storage Discussion

## Critical Question

**"How do we get summary text from embeddings to feed to prompt?"**

**"Should we store plain summary WITH embeddings or only embeddings?"**

---

## The Fundamental Problem

### Embeddings Are ONE-WAY

**Key Fact**: You **CANNOT** reconstruct the original text from an embedding vector.

```
Text → Embedding ✅ (possible)
Embedding → Text ❌ (impossible)
```

**Why?**
- Embeddings are dense vector representations
- They capture semantic meaning, not exact text
- Multiple different texts can have similar embeddings
- Information is lost in the transformation

**Example**:
```
Text 1: "We discussed sleep schedule and aiming for 8 hours"
Text 2: "Talked about getting 8 hours of sleep and sleep schedule"
Embedding: [0.1, 0.2, 0.3, ...] (similar for both)
```

You can't tell which exact text it was from the embedding alone!

---

## Answer: MUST Store Summary WITH Embeddings

### Why Both Are Needed

| Component | Purpose | Can Reconstruct? |
|-----------|---------|------------------|
| **Embedding** | Similarity search | ❌ No - can't get text back |
| **Summary Text** | Prompt injection | ✅ Yes - this is what we need |

### The Flow

```
1. Store: summary + embedding (together)
   ↓
2. Use embedding for: Similarity search (find relevant sessions)
   ↓
3. Use summary text for: Prompt injection (feed to LLM)
```

---

## Current Implementation Analysis

### What We Store

**In Supabase**:
```sql
CREATE TABLE sessions (
    summary TEXT,        -- ✅ The actual text
    embedding vector(384)  -- ✅ For similarity search
)
```

**In Shadow Memory**:
```python
self.cached_embeddings = [
    {
        "summary": "We discussed sleep...",  # ✅ Text for prompt
        "embedding": [0.1, 0.2, ...]        # ✅ For similarity search
    }
]
```

**In Embedding Cache**:
```python
_embedding_cache.set_embedding(
    summary_text,      # Key: summary text
    embedding_vector   # Value: embedding
)
```

### How We Use Them

**Step 1: Similarity Search** (uses embedding)
```python
# Calculate similarity using embeddings
similarity = cosine_similarity(query_embedding, session_embedding)
```

**Step 2: Get Summary Text** (uses summary)
```python
# Extract summary text from match
summary_text = match["summary"]  # ← This is what we inject!
```

**Step 3: Inject into Prompt** (uses summary text)
```python
# Format and inject summary text
context_text = f"## PAST SESSION\n{summary_text}\n"
inject_past_context(context, sessions)
```

---

## Storage Options Comparison

### Option 1: Store Summary + Embedding ✅ (Current - BEST)

**Storage**:
```python
{
    "summary": "We discussed sleep schedule...",  # Text
    "embedding": [0.1, 0.2, ...]                 # Vector
}
```

**Pros**:
- ✅ Can do similarity search (embedding)
- ✅ Can inject into prompt (summary text)
- ✅ Complete solution
- ✅ Fast (everything in memory)

**Cons**:
- ⚠️ Slightly more memory (~2KB per session vs ~1.5KB)

**Memory**: ~2KB per session (summary ~500 bytes + embedding ~1.5KB)

---

### Option 2: Store Only Embeddings ❌ (NOT VIABLE)

**Storage**:
```python
{
    "embedding": [0.1, 0.2, ...]  # Only vector
}
```

**Pros**:
- ✅ Less memory (~1.5KB per session)
- ✅ Fast similarity search

**Cons**:
- ❌ **CANNOT get summary text back!**
- ❌ Would need to query Supabase for text (defeats purpose)
- ❌ Slower (network call needed)
- ❌ Incomplete solution

**Memory**: ~1.5KB per session (but useless without text!)

---

### Option 3: Store Only Summary Text ❌ (NOT VIABLE)

**Storage**:
```python
{
    "summary": "We discussed sleep..."  # Only text
}
```

**Pros**:
- ✅ Can inject into prompt
- ✅ Less memory (~500 bytes per session)

**Cons**:
- ❌ **Cannot do similarity search!**
- ❌ Would need to generate embeddings on-demand (slow)
- ❌ No semantic search capability

**Memory**: ~500 bytes per session (but can't search!)

---

## Recommendation: Store BOTH ✅

### Why Both Are Essential

1. **Embedding** → For similarity search (find relevant sessions)
2. **Summary Text** → For prompt injection (feed to LLM)

**They serve different purposes and both are needed!**

---

## Memory Analysis

### Per Session Storage

| Component | Size | Purpose |
|-----------|------|---------|
| Summary text | ~500 bytes | Prompt injection |
| Embedding vector | ~1,536 bytes (384 floats × 4) | Similarity search |
| Metadata | ~200 bytes | Context (optional) |
| **Total** | **~2.2 KB** | Both needed |

### For 3-4 Sessions

- **Total**: ~6.6-8.8 KB per user
- **Very lightweight** for the functionality provided

---

## Current Implementation (Correct Approach)

### What We Fetch

```python
# Fetch summary + embedding (both needed!)
result = client.table("sessions")
    .select("summary, embedding")  # ← Both!
    .execute()
```

### What We Store

```python
# In Shadow Memory
self.cached_embeddings = [
    {
        "summary": "...",      # ← For prompt injection
        "embedding": [...]     # ← For similarity search
    }
]
```

### How We Use

```python
# Step 1: Search using embeddings
similarity = cosine_similarity(query_embedding, session_embedding)

# Step 2: Get summary text from match
summary_text = match["summary"]  # ← Extract text

# Step 3: Inject text into prompt
inject_past_context(context, [{"summary": summary_text, ...}])
```

---

## Conclusion

### Answer to Your Questions

1. **"How do we get summary text from embeddings?"**
   - ❌ **We DON'T** - embeddings can't be converted back to text
   - ✅ **We store summary text ALONG WITH embeddings**
   - ✅ **We use embedding for search, summary text for injection**

2. **"Should we store plain summary WITH embeddings or only embeddings?"**
   - ✅ **Store BOTH** - they serve different purposes
   - ✅ **Embedding**: For similarity search
   - ✅ **Summary Text**: For prompt injection
   - ❌ **Only embeddings**: Can't inject into prompt (no text!)
   - ❌ **Only summary**: Can't do semantic search (no vectors!)

### Current Implementation: ✅ CORRECT

We already store both:
- ✅ Summary text (for prompt injection)
- ✅ Embedding vector (for similarity search)

**This is the right approach!**

---

## Code Flow

```
1. Fetch: summary + embedding (from Supabase)
   ↓
2. Store: Both in Shadow Memory
   ↓
3. Search: Use embedding for similarity
   ↓
4. Extract: Get summary text from match
   ↓
5. Inject: Use summary text in prompt
```

**Both are needed at different stages!**

