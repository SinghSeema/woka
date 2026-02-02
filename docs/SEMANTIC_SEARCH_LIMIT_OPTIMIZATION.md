# Semantic Search Limit Optimization

## Problem

**Issue**: `MAX_DYNAMIC_SESSIONS` (default: 2-3) was being used for **all** query types, including semantic search.

**Why This Is Wrong**:
- ❌ Semantic search uses similarity scores (threshold filters quality)
- ❌ 2-3 results is too restrictive for semantic search
- ❌ Threshold already filters out low-quality matches
- ❌ More results = better chance of finding relevant content

---

## Solution

**Created separate limit for semantic search**: `MAX_SEMANTIC_SEARCH_RESULTS`

### Configuration

**Location**: `backend/app/core/config.py`

```python
MAX_DYNAMIC_SESSIONS: int = Field(
    default=2, description="Max sessions to retrieve dynamically (for date/topic queries)"
)
MAX_SEMANTIC_SEARCH_RESULTS: int = Field(
    default=5, description="Max sessions to retrieve for semantic search (higher because threshold filters quality)"
)
```

### Usage

**Location**: `backend/bot/services/past_context_processor.py`

**Before**:
```python
sessions = await get_sessions_by_semantic_search(
    self._user_name,
    intent.query_text,
    limit=settings.MAX_DYNAMIC_SESSIONS,  # ❌ Only 2-3 results
    ...
)
```

**After**:
```python
# Use higher limit for semantic search (threshold filters quality)
semantic_limit = getattr(settings, "MAX_SEMANTIC_SEARCH_RESULTS", 5)
sessions = await get_sessions_by_semantic_search(
    self._user_name,
    intent.query_text,
    limit=semantic_limit,  # ✅ 5 results (default)
    ...
)
```

---

## Why Different Limits?

### Date/Topic Queries (MAX_DYNAMIC_SESSIONS = 2-3)

**Characteristics**:
- Exact matches (date ranges, keywords)
- Less precise filtering
- Fewer results needed
- Lower limit is appropriate

**Example**:
- "What did we discuss on January 15?"
- "Tell me about sessions about sleep"

### Semantic Search (MAX_SEMANTIC_SEARCH_RESULTS = 5)

**Characteristics**:
- Similarity-based matching
- Threshold filters quality (0.7+ similarity)
- More results = better coverage
- Higher limit is appropriate

**Example**:
- "What did we discuss about sleep?"
- "Tell me about our past conversations"

---

## Benefits

### 1. Better Coverage ✅

**Before**: Only 2-3 semantic search results
**After**: 5 semantic search results (default)

**Impact**: More relevant sessions found, better context for LLM

### 2. Quality Filtering ✅

**Threshold Already Filters**:
- Only results with similarity ≥ 0.7 are returned
- Low-quality matches are automatically excluded
- Higher limit doesn't mean lower quality

**Example**:
```
Query: "What did we discuss about sleep?"
Results:
  - Session 1: similarity=0.92 ✅ (about sleep schedule)
  - Session 2: similarity=0.85 ✅ (about sleep habits)
  - Session 3: similarity=0.78 ✅ (about sleep quality)
  - Session 4: similarity=0.65 ❌ (below threshold, excluded)
  - Session 5: similarity=0.71 ✅ (about sleep routine)
```

### 3. Flexible Configuration ✅

**Can Adjust Per Use Case**:
```bash
# In .env file
MAX_DYNAMIC_SESSIONS=2          # For date/topic queries
MAX_SEMANTIC_SEARCH_RESULTS=5   # For semantic search
```

---

## Comparison

| Query Type | Limit Setting | Default | Why |
|------------|---------------|---------|-----|
| **Date Range** | `MAX_DYNAMIC_SESSIONS` | 2 | Exact matches, fewer needed |
| **Topic (Keyword)** | `MAX_DYNAMIC_SESSIONS` | 2 | Keyword matching, less precise |
| **Semantic Search** | `MAX_SEMANTIC_SEARCH_RESULTS` | 5 | Similarity-based, threshold filters quality |

---

## Configuration

### Default Values

```python
MAX_DYNAMIC_SESSIONS = 2          # For date/topic queries
MAX_SEMANTIC_SEARCH_RESULTS = 5   # For semantic search
```

### Customization

**In `.env` file**:
```bash
# For date/topic queries (exact matches)
MAX_DYNAMIC_SESSIONS=2

# For semantic search (similarity-based)
MAX_SEMANTIC_SEARCH_RESULTS=5
```

**Adjust based on**:
- User needs (more/less context)
- Token limits
- Performance requirements

---

## Impact

### Before

```
Semantic Search Query:
  - Limit: 2-3 results
  - Threshold: 0.7
  - Result: Only 2-3 relevant sessions (might miss important context)
```

### After

```
Semantic Search Query:
  - Limit: 5 results (default)
  - Threshold: 0.7
  - Result: Up to 5 relevant sessions (better coverage)
  - Quality: Still filtered by threshold (only high-quality matches)
```

---

## Summary

✅ **Separated limits** for different query types
✅ **Higher limit** for semantic search (5 vs 2-3)
✅ **Threshold still filters** quality (only similarity ≥ 0.7)
✅ **Better coverage** without sacrificing quality
✅ **Flexible configuration** via settings

**Result**: Semantic search now returns more relevant results while maintaining quality through threshold filtering!

