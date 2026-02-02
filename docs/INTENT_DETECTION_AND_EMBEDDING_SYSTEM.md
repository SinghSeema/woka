# Intent Detection and Embedding System Documentation

## Overview

This document explains the intent detection technique, embedding generation, embedding matching, and fallback mechanisms used in the PipecatBot system for retrieving past conversation context.

---

## 1. Intent Detection Technique

**Location**: `backend/bot/services/intent_detector.py`

**Method**: Keyword-based pattern matching with regex patterns

### How It Works

#### Step 1: Keyword Detection
The system checks for past-reference keywords in the user's message:
- `'what did we'`, `'what did i'`, `'what was'`, `'what were'`
- `'tell me about'`, `'remind me'`, `'remember when'`
- `'last time'`, `'before'`, `'previous'`, `'earlier'`, `'past'`
- `'ago'`, `'yesterday'`, `'last week'`, `'last month'`
- `'did we discuss'`, `'did we talk'`, `'did i mention'`
- `'what progress'`, `'how am i doing'`, `'my goal'`
- `'on [date]'`, `'in [month]'`, `'during'`
- `'past sessions'`, `'past conversations'`, `'what we discussed'`

#### Step 2: Intent Classification
The system categorizes detected intents into types:

- **`date`**: Date-specific queries (e.g., "yesterday", "last week", "3 days ago")
  - Confidence: 0.8
  - Uses regex patterns to detect date references

- **`topic`**: Topic-specific queries (e.g., "about sleep", "regarding exercise")
  - Confidence: 0.7
  - Detects keywords like 'about', 'regarding', 'concerning', 'related to'

- **`progress`**: Progress/goal queries (e.g., "what progress", "my goal")
  - Confidence: 0.75
  - Detects keywords: 'progress', 'goal'

- **`general`**: General past reference queries
  - Confidence: 0.6-0.8
  - Default fallback when no specific type is detected

#### Step 3: Information Extraction

**Topic Extraction** (`_extract_topics`):
- Extracts wellness-related keywords: sleep, nutrition, diet, exercise, workout, fitness, stress, anxiety, mental health, meditation, mindfulness, weight, health, wellness, habits, routine, schedule, energy, mood, pain, injury, recovery, illness, symptoms, medicine, medication, doctor, treatment
- Uses regex patterns to find topics after "about", "regarding", "discuss", "talked about"
- Filters out stop words (the, a, an, and, or, but, in, on, at, to, for, of, with, by, we, did, do, what, when, where, how, why, etc.)

**Date Range Extraction** (`_extract_date_range`):
- Parses relative dates:
  - `'yesterday'` → Previous day (00:00 to 23:59)
  - `'last week'` → Previous week (Monday to Sunday)
  - `'last month'` → Previous month (first day to last day)
  - `'X days ago'` → Specific date (00:00 to 23:59)
- Returns dictionary with `'start'` and `'end'` datetime objects

#### Step 4: Confidence Scoring
- Base confidence: 0.5
- Date match: 0.8
- Topic match: 0.7
- Progress match: 0.75
- General match: 0.6-0.8

### Example

```python
# Input: "What did we discuss about sleep yesterday?"
# Output:
PastReferenceIntent(
    has_intent=True,
    intent_type="topic",  # (with date context)
    topics=["sleep"],
    date_range={
        'start': datetime(2024-01-15 00:00:00),
        'end': datetime(2024-01-15 23:59:59)
    },
    query_text="What did we discuss about sleep yesterday?",
    confidence=0.7
)
```

---

## 2. Embedding Generation & Matching

### Embedding Generation

**Location**: `backend/bot/services/embedding_service.py`

**Technique**: Two-tier approach with automatic fallback

#### Primary Method: OpenAI Embeddings API

**Models Supported**:
- `text-embedding-3-large`: 3072 dimensions
- `text-embedding-3-small`: 1536 dimensions
- `text-embedding-ada-002`: 1536 dimensions

**Process**:
1. Checks if OpenAI API key is available
2. Makes HTTP POST request to `https://api.openai.com/v1/embeddings`
3. Returns embedding vector as list of floats

**Error Handling**:
- Rate limit (429): Falls back to local model
- Network errors: Falls back to local model
- API errors: Falls back to local model

#### Fallback Method: Local Sentence Transformers

**Model**: `all-MiniLM-L6-v2` (default)
- Dimensions: 384
- Library: `sentence-transformers`
- Runs in async thread pool to avoid blocking event loop

**Process**:
1. Loads model on first use (cached globally)
2. Encodes text using `SentenceTransformer.encode()`
3. Converts numpy array to Python list
4. Returns embedding vector

#### Caching Strategy

**Embedding Cache** (`ContextCache`):
- Stores embeddings by text content
- Prevents regenerating embeddings for same text
- Checked before generation: `_embedding_cache.get_embedding(text)`
- Updated after generation: `_embedding_cache.set_embedding(text, embedding)`

**Code Flow**:
```python
generate_embedding(text)
  ↓
Check cache first
  ↓
[Cache Hit?]
  ├─ Yes → Return cached embedding
  └─ No → Try OpenAI API
          ↓
      [Success?]
          ├─ Yes → Cache and return
          └─ No → Try local model
                  ↓
              [Success?]
                  ├─ Yes → Cache and return
                  └─ No → Return None
```

### Embedding Matching

**Location**: `backend/bot/services/database_service.py`

**Technique**: Cosine Similarity

#### Similarity Calculation

**Function**: `cosine_similarity(vec1, vec2)`

**Formula**:
```
similarity = dot_product(vec1, vec2) / (norm(vec1) * norm(vec2))
```

**Implementation**:
- Uses NumPy for efficient computation (if available)
- Falls back to manual calculation if NumPy unavailable
- Returns value between 0.0 and 1.0
- Handles edge cases (zero vectors)

**Code**:
```python
def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    dot_product = np.dot(vec1, vec2)
    norm_a = np.linalg.norm(vec1)
    norm_b = np.linalg.norm(vec2)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    similarity = dot_product / (norm_a * norm_b)
    return max(0.0, min(1.0, similarity))
```

#### Search Strategy: Two-Tier Approach

**Tier 1: Local Cache Search** (Fast Path - 1-5ms)

**Location**: `search_cached_embeddings()`

**Process**:
1. Retrieves cached embeddings from Shadow Memory
2. For each cached embedding:
   - Calculates cosine similarity with query embedding
   - Checks if similarity >= threshold (default: 0.7)
   - Adds to matches if above threshold
3. Sorts matches by similarity (highest first)
4. Returns top N matches (default: 5)

**Advantages**:
- No network call
- Very fast (1-5ms vs 200-500ms for DB)
- No database load
- Works offline

**Tier 2: Supabase Vector Search** (Fallback - 200-500ms)

**Location**: `get_sessions_by_semantic_search()`

**Process**:
1. Generates query embedding
2. Calls Supabase RPC function `match_sessions`
3. Uses `pgvector` extension for vector similarity search
4. Filters by user name
5. Returns top N matches above threshold

**Database Function**:
```sql
match_sessions(
    query_embedding: vector,
    match_threshold: float,
    match_count: int,
    filter_user_name: text
)
```

**Advantages**:
- Searches entire database
- Handles large datasets
- Uses optimized vector indexes

#### Matching Process Flow

```python
# For each stored embedding:
similarity = cosine_similarity(query_embedding, stored_embedding)

if similarity >= threshold (0.7):
    matches.append({
        "summary": summary_text,
        "similarity": similarity,
        "embedding": embedding
    })

# Sort by similarity (highest first)
matches.sort(key=lambda x: x["similarity"], reverse=True)

# Return top N matches
return matches[:limit]
```

---

## 3. Fallback Mechanisms

The system implements **5 layers of fallback mechanisms** to ensure reliability:

### Layer 1: Embedding Generation Fallback

**Location**: `embedding_service.py` → `generate_embedding()`

**Flow**:
```
OpenAI API → Local Model → Return None
```

**Details**:
- If OpenAI API fails (rate limit, network error, API error) → falls back to local model
- If local model fails (import error, model load error) → returns `None`
- When `None` is returned, semantic search is disabled for that query

**Error Types Handled**:
- HTTP 429 (Rate Limit)
- Network timeouts
- API key missing
- Model not found
- Import errors (httpx, sentence-transformers)

### Layer 2: Semantic Search Fallback

**Location**: `database_service.py` → `get_sessions_by_semantic_search()`

**Flow**:
```
Local Cache Search → Supabase Vector Search → Return Empty
```

**Details**:
1. **First**: Tries local cached embeddings (fast, no network)
2. **If no matches or cache unavailable**: Queries Supabase vector search
3. **If Supabase fails**: Returns empty list

**Fallback Triggers**:
- No cached embeddings available
- Local search finds no matches above threshold
- Supabase client not available
- Database query fails

### Layer 3: Search Strategy Fallback

**Location**: `past_context_processor.py` → `_handle_fetch()`

**Flow**:

**For Topic Queries**:
```
Semantic Search → Keyword Search → Most Recent Sessions
```

1. **First**: Try semantic search (with topic-based query construction)
2. **If no results**: Try keyword search (`get_sessions_by_topic`)
3. **If still no results**: Return most recent sessions

**For General Queries**:
```
Semantic Search → Most Recent Sessions
```

1. **First**: Try semantic search
2. **If no results**: Return most recent sessions

**Topic Query Optimization**:
- Constructs query from extracted topics (filters stop words)
- Uses lower threshold (0.6 vs 0.7) for better recall
- Falls back to full query text if topic extraction fails

### Layer 4: Intent Detection Fallback

**Location**: `context_manager.py` → `handle_intent_detection_fallback()`

**Flow**:
```
Pattern Matching → Keyword Fallback
```

**Details**:
- If pattern matching fails → simple keyword check
- Keywords checked: `'past'`, `'before'`, `'last time'`, `'previous'`, `'earlier'`, `'ago'`
- Returns lower confidence (0.5) but still processes the query
- Intent type: `'general'`

**Use Case**:
- Handles edge cases where regex patterns don't match
- Ensures queries aren't missed due to pattern limitations

### Layer 5: Query Failure Fallback

**Location**: `context_manager.py` → `handle_query_failure()`

**Flow**:
```
Query Error → Pre-loaded Sessions → Empty Results
```

**Details**:
- If Supabase query fails (exception) → uses pre-loaded fallback sessions if available
- Otherwise returns empty results
- Logs error for debugging

**Error Handling**:
- Catches all exceptions from database queries
- Logs error with context (query type, user name)
- Returns graceful fallback instead of crashing

---

## Complete System Flow Diagram

```
User Message
    ↓
Intent Detection (keyword + regex)
    ↓
[Has Intent?]
    ├─ No → Skip context fetch
    └─ Yes → Check Context Cache
            ↓
        [Cache Hit?]
            ├─ Yes → Use cached sessions
            └─ No → Generate Query Embedding
                    ↓
                [Embedding Generated?]
                    ├─ No → Fallback to keyword search
                    └─ Yes → Search Local Cache (cosine similarity)
                            ↓
                        [Found Matches?]
                            ├─ Yes → Return matches
                            └─ No → Query Supabase (vector search)
                                    ↓
                                [Found Matches?]
                                    ├─ Yes → Return matches
                                    └─ No → Fallback to keyword search
                                            ↓
                                        [Found Matches?]
                                            ├─ Yes → Return matches
                                            └─ No → Return most recent sessions
                                                    ↓
                                                Inject into System Prompt
```

---

## Key Components Summary

| Component | Location | Technique | Purpose |
|-----------|----------|-----------|---------|
| **Intent Detection** | `intent_detector.py` | Keyword + Regex | Identify past reference queries |
| **Embedding Generation** | `embedding_service.py` | OpenAI API / Local Model | Convert text to vectors |
| **Embedding Matching** | `database_service.py` | Cosine Similarity | Find similar past sessions |
| **Local Search** | `database_service.py` | Cosine Similarity (cached) | Fast local matching |
| **Vector Search** | Supabase RPC | pgvector | Database vector search |
| **Fallback Handler** | `context_manager.py` | Multiple strategies | Ensure reliability |

---

## Performance Characteristics

| Operation | Typical Time | Notes |
|-----------|--------------|-------|
| Intent Detection | <1ms | Pure Python, no I/O |
| Embedding Generation (OpenAI) | 50-200ms | Network call |
| Embedding Generation (Local) | 10-50ms | CPU-bound, cached model |
| Local Cache Search | 1-5ms | In-memory computation |
| Supabase Vector Search | 200-500ms | Network + DB query |
| Keyword Search | 100-300ms | Database query |
| Most Recent Sessions | 100-300ms | Simple DB query |

---

## Configuration Settings

**Relevant Settings** (in `app/core/config.py`):
- `ENABLE_SEMANTIC_SEARCH`: Enable/disable semantic search
- `ENABLE_DYNAMIC_CONTEXT`: Enable/disable dynamic context injection
- `EMBEDDING_MODEL`: OpenAI model name or "local"
- `LOCAL_EMBEDDING_MODEL`: Local model name (default: "all-MiniLM-L6-v2")
- `EMBEDDING_DIMENSION`: Expected embedding dimension (384 or 1536)
- `SEMANTIC_SEARCH_THRESHOLD`: Minimum similarity threshold (default: 0.7)
- `MAX_SEMANTIC_SEARCH_RESULTS`: Maximum results to return (default: 5)
- `MAX_DYNAMIC_SESSIONS`: Maximum sessions for fallback (default: 2)

---

## Best Practices

1. **Caching**: Always use embedding cache to avoid regenerating embeddings
2. **Threshold Tuning**: Adjust similarity threshold based on use case:
   - Higher (0.8-0.9): More precise, fewer results
   - Lower (0.5-0.6): More recall, more results
3. **Local Search First**: Always try local cache before database query
4. **Error Handling**: Always have fallback strategies for each layer
5. **Monitoring**: Log similarity scores and match counts for debugging

---

## Troubleshooting

### Low Similarity Scores
- **Cause**: Embeddings not normalized, different models used, semantic mismatch
- **Solution**: Check embedding dimensions, ensure same model for query and stored embeddings

### No Matches Found
- **Cause**: Threshold too high, query too short, no relevant sessions
- **Solution**: Lower threshold, expand query text, check database has sessions

### Slow Performance
- **Cause**: Too many database queries, no caching
- **Solution**: Enable local cache, use Shadow Memory, reduce query frequency

### Embedding Generation Fails
- **Cause**: API key missing, network issues, model not installed
- **Solution**: Check API key, verify network, install sentence-transformers

---

## References

- **Intent Detection**: `backend/bot/services/intent_detector.py`
- **Embedding Service**: `backend/bot/services/embedding_service.py`
- **Database Service**: `backend/bot/services/database_service.py`
- **Context Processor**: `backend/bot/services/past_context_processor.py`
- **Context Manager**: `backend/bot/services/context_manager.py`

---

## Related Documentation

- `PLAN_PAST_REFERENCE_SYSTEM.md` - Overall system design
- `LOCAL_EMBEDDING_SEARCH_OPTIMIZATION.md` - Local cache optimization
- `EMBEDDING_VS_SUMMARY_STORAGE_DISCUSSION.md` - Storage strategy
- `DYNAMIC_QUERY_TROUBLESHOOTING.md` - Troubleshooting guide
- `SEMANTIC_SEARCH_LIMIT_OPTIMIZATION.md` - Performance tuning

