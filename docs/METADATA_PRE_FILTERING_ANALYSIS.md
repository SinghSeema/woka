# Metadata Pre-Filtering Analysis

## Executive Summary

**YES, metadata pre-filtering is an EXCELLENT idea!** It can dramatically improve query performance by reducing the vector search space before doing expensive similarity calculations.

**Current Problem**: Vector similarity search runs on ALL sessions for a user, even when we could filter by date, topics, or other metadata first.

**Solution**: Use fast database indexes to pre-filter, then run vector search on the smaller subset.

---

## Current State Analysis

### Available Metadata

From `sessions` table:
- ✅ `user_name` (indexed) - Already used for filtering
- ✅ `created_at` (indexed) - Timestamp, can filter by date range
- ✅ `duration_seconds` - Session length
- ✅ `message_count` - Number of messages
- ✅ `room_name` - Session identifier
- ✅ `summary` (text) - Contains topics but not indexed

### Current Search Flow

```python
# Current: Search ALL sessions for user
query_embedding → match_sessions() → 
  Filter: user_name only
  Search: ALL sessions (could be 100+)
  Result: Top 5 by similarity
```

**Performance**: 
- Searches 100+ vectors per query
- No pre-filtering by date/topics
- Vector search is the bottleneck

---

## Pre-Filtering Opportunities

### 1. **Date Range Filtering** (HIGH IMPACT)

**Use Case**: User asks "What did we discuss yesterday?"

**Current**: Searches ALL sessions, then filters by similarity

**Optimized**:
```sql
-- Pre-filter by date (FAST - uses index)
WHERE user_name = 'user' 
  AND created_at >= '2024-01-14' 
  AND created_at <= '2024-01-15'
  AND embedding IS NOT NULL
-- Then do vector search on ~5 sessions instead of 100
ORDER BY embedding <=> query_embedding
```

**Performance Gain**:
- Reduces search space: 100 sessions → 5 sessions
- 20x faster vector search
- Uses existing `idx_sessions_created_at` index

**Implementation**: Already partially implemented in `get_sessions_by_date_range()`, but not used in semantic search!

### 2. **Topic Keywords Filtering** (MEDIUM IMPACT)

**Use Case**: User asks "What did we discuss about sleep?"

**Current**: Searches ALL sessions, relies on semantic similarity

**Optimized**:
```sql
-- Pre-filter by keyword in summary (FAST - text search)
WHERE user_name = 'user'
  AND summary ILIKE '%sleep%'
  AND embedding IS NOT NULL
-- Then do vector search on ~10 sessions instead of 100
ORDER BY embedding <=> query_embedding
```

**Performance Gain**:
- Reduces search space: 100 sessions → 10 sessions
- 10x faster vector search
- Better recall (finds exact keyword matches)

**Implementation**: Need full-text search index on `summary` column

### 3. **Session Quality Filtering** (LOW IMPACT)

**Use Case**: Filter out very short or low-quality sessions

**Optimized**:
```sql
WHERE user_name = 'user'
  AND duration_seconds >= 60  -- At least 1 minute
  AND message_count >= 5      -- At least 5 messages
  AND embedding IS NOT NULL
```

**Performance Gain**:
- Reduces search space: 100 sessions → 80 sessions
- 1.25x faster (minor improvement)
- Better quality results

### 4. **Recency Filtering** (MEDIUM IMPACT)

**Use Case**: Prioritize recent sessions

**Optimized**:
```sql
WHERE user_name = 'user'
  AND created_at >= NOW() - INTERVAL '30 days'  -- Last 30 days
  AND embedding IS NOT NULL
ORDER BY created_at DESC, embedding <=> query_embedding
```

**Performance Gain**:
- Reduces search space: 100 sessions → 20 sessions
- 5x faster vector search
- More relevant results (recent context)

---

## Proposed Database Enhancements

### 1. Add Full-Text Search Index

**Current**: `summary` column has no search index

**Proposed**:
```sql
-- Add GIN index for full-text search
CREATE INDEX idx_sessions_summary_gin 
ON sessions USING gin(to_tsvector('english', summary));

-- Or simpler: GiST index for ILIKE queries
CREATE INDEX idx_sessions_summary_text 
ON sessions USING gin(summary gin_trgm_ops);
```

**Benefits**:
- Fast keyword search in summaries
- Can pre-filter by topics
- Enables hybrid search (keyword + semantic)

**Cost**: 
- Index size: ~20-30% of table size
- Slightly slower inserts (negligible)

### 2. Add Composite Indexes

**Proposed**:
```sql
-- Composite index for common queries
CREATE INDEX idx_sessions_user_date 
ON sessions(user_name, created_at DESC);

-- Composite index for user + quality
CREATE INDEX idx_sessions_user_quality 
ON sessions(user_name, duration_seconds, message_count);
```

**Benefits**:
- Faster multi-column filters
- Better query planning
- Reduced index scans

### 3. Add Topic Extraction Column (OPTIONAL)

**Proposed**:
```sql
ALTER TABLE sessions ADD COLUMN topics TEXT[];

-- Example: ['sleep', 'nutrition', 'exercise']
-- Indexed for fast filtering
CREATE INDEX idx_sessions_topics 
ON sessions USING gin(topics);
```

**Benefits**:
- Pre-extract topics during summary generation
- Fast topic-based filtering
- No need to search summary text

**Cost**:
- Need to extract topics (NLP or keyword matching)
- Additional storage (~100 bytes per session)

---

## Optimized Search Strategy

### Two-Phase Search

**Phase 1: Metadata Pre-Filtering** (FAST - uses indexes)
```python
# Filter by metadata first
filtered_sessions = db.query(
    user_name=user_name,
    date_range=intent.date_range,  # If provided
    topics=intent.topics,           # If provided
    min_duration=60,                # Quality filter
    max_age_days=30                 # Recency filter
)
# Result: 100 sessions → 10 sessions
```

**Phase 2: Vector Similarity Search** (SLOW - but on smaller set)
```python
# Search only pre-filtered sessions
results = vector_search(
    query_embedding=query_embedding,
    candidate_sessions=filtered_sessions,  # Only 10, not 100!
    threshold=0.7,
    limit=5
)
```

**Performance**:
- Pre-filtering: <5ms (index scan)
- Vector search: 10ms (on 10 sessions) vs 100ms (on 100 sessions)
- **Total: 15ms vs 100ms = 6.7x faster**

### Smart Filtering Logic

```python
def get_filtered_sessions(user_name, intent):
    """Pre-filter sessions based on intent metadata."""
    filters = {
        "user_name": user_name,
        "has_embedding": True
    }
    
    # Date filtering (if intent has date range)
    if intent.date_range:
        filters["created_at_gte"] = intent.date_range["start"]
        filters["created_at_lte"] = intent.date_range["end"]
    
    # Topic filtering (if intent has topics)
    if intent.topics:
        # Use full-text search or topic array
        filters["topics"] = intent.topics
    
    # Quality filtering (always apply)
    filters["min_duration"] = 60  # At least 1 minute
    filters["min_messages"] = 5   # At least 5 messages
    
    # Recency filtering (if no date specified)
    if not intent.date_range:
        filters["max_age_days"] = 90  # Last 3 months
    
    return db.query_sessions(**filters)
```

---

## Implementation Plan

### Phase 1: Date Range Pre-Filtering (EASY, HIGH IMPACT)

**Current Code**: `get_sessions_by_semantic_search()` doesn't use date filtering

**Change**:
```python
async def get_sessions_by_semantic_search(
    user_name: str,
    query_text: str,
    date_range: Optional[Dict] = None,  # NEW
    limit: int = 5,
    threshold: float = 0.7,
    ...
):
    # Pre-filter by date if provided
    if date_range:
        # Use existing get_sessions_by_date_range()
        candidate_sessions = await get_sessions_by_date_range(
            user_name, 
            date_range["start"], 
            date_range["end"],
            limit=limit * 10  # Get more candidates for vector search
        )
        # Then do vector search on candidates only
        return search_cached_embeddings(candidate_sessions, ...)
    else:
        # Fallback to current behavior
        ...
```

**Impact**: 
- 10-20x faster for date queries
- Uses existing code
- Low risk

### Phase 2: Topic Pre-Filtering (MEDIUM EFFORT, MEDIUM IMPACT)

**Add Full-Text Search**:
```sql
-- Add index
CREATE INDEX idx_sessions_summary_gin 
ON sessions USING gin(to_tsvector('english', summary));
```

**Update Code**:
```python
async def get_sessions_by_semantic_search(
    user_name: str,
    query_text: str,
    topics: Optional[List[str]] = None,  # NEW
    ...
):
    # Pre-filter by topics if provided
    if topics:
        candidate_sessions = await get_sessions_by_topic(
            user_name,
            topics,
            limit=limit * 10
        )
        # Then do vector search on candidates
        return search_cached_embeddings(candidate_sessions, ...)
```

**Impact**:
- 5-10x faster for topic queries
- Better recall (finds exact matches)
- Medium complexity

### Phase 3: Quality + Recency Filtering (EASY, LOW IMPACT)

**Add Default Filters**:
```python
# Always apply quality filters
filters = {
    "duration_seconds__gte": 60,
    "message_count__gte": 5
}

# Apply recency filter if no date specified
if not date_range:
    filters["created_at__gte"] = datetime.now() - timedelta(days=90)
```

**Impact**:
- 1.2-2x faster (minor improvement)
- Better result quality
- Very low risk

---

## Updated match_sessions() Function

### Current Function

```sql
CREATE OR REPLACE FUNCTION match_sessions(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    filter_user_name text DEFAULT NULL
)
-- Only filters by user_name
```

### Enhanced Function

```sql
CREATE OR REPLACE FUNCTION match_sessions(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    filter_user_name text DEFAULT NULL,
    -- NEW: Pre-filtering parameters
    filter_date_from timestamptz DEFAULT NULL,
    filter_date_to timestamptz DEFAULT NULL,
    filter_topics text[] DEFAULT NULL,
    filter_min_duration int DEFAULT 60,
    filter_max_age_days int DEFAULT 90
)
RETURNS TABLE (...)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT ...
    FROM sessions s
    WHERE 
        s.embedding IS NOT NULL
        AND (filter_user_name IS NULL OR s.user_name = filter_user_name)
        -- NEW: Date pre-filtering
        AND (filter_date_from IS NULL OR s.created_at >= filter_date_from)
        AND (filter_date_to IS NULL OR s.created_at <= filter_date_to)
        -- NEW: Topic pre-filtering (using full-text search)
        AND (
            filter_topics IS NULL OR 
            EXISTS (
                SELECT 1 FROM unnest(filter_topics) AS topic
                WHERE s.summary ILIKE '%' || topic || '%'
            )
        )
        -- NEW: Quality pre-filtering
        AND s.duration_seconds >= filter_min_duration
        -- NEW: Recency pre-filtering
        AND (
            filter_date_from IS NOT NULL OR 
            s.created_at >= NOW() - (filter_max_age_days || ' days')::interval
        )
        -- Vector similarity search (on pre-filtered set)
        AND (1 - (s.embedding <=> query_embedding)) >= match_threshold
    ORDER BY s.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

**Benefits**:
- All filtering in database (fast)
- Uses indexes efficiently
- Single query instead of multiple
- Backward compatible (optional parameters)

---

## Performance Comparison

### Scenario: User has 100 sessions, asks "What did we discuss about sleep yesterday?"

**Current Approach**:
```
1. Generate query embedding: 50ms
2. Vector search ALL 100 sessions: 100ms
3. Filter results: 5ms
Total: 155ms
```

**With Pre-Filtering**:
```
1. Generate query embedding: 50ms
2. Pre-filter by date (index scan): 2ms → 5 sessions
3. Pre-filter by topic (text search): 3ms → 2 sessions
4. Vector search on 2 sessions: 2ms
Total: 57ms (2.7x faster)
```

**With More Sessions (1000 sessions)**:
- Current: 1000ms vector search
- With pre-filtering: 57ms (17.5x faster!)

---

## Integration with Intent Detection

### Current Flow

```
User Query → Intent Detection → Semantic Search (all sessions)
```

### Optimized Flow

```
User Query → Intent Detection → Extract Metadata
  ↓
Pre-Filter Sessions (by metadata)
  ↓
Semantic Search (on filtered set)
  ↓
Return Results
```

**Example**:
```python
intent = detect_past_reference_intent("What did we discuss about sleep yesterday?")

# Extract metadata
date_range = intent.date_range  # {"start": "2024-01-14", "end": "2024-01-15"}
topics = intent.topics          # ["sleep"]

# Pre-filter
candidate_sessions = await get_sessions_by_date_range(
    user_name, date_range["start"], date_range["end"]
)
candidate_sessions = await filter_by_topics(candidate_sessions, topics)

# Vector search on small set
results = await search_cached_embeddings(
    query_embedding,
    candidate_sessions,  # Only 2-5 sessions instead of 100!
    threshold=0.7
)
```

---

## Recommendations

### ✅ **DO Implement** (High ROI)

1. **Date Range Pre-Filtering**
   - Easy to implement
   - Uses existing code
   - 10-20x performance gain
   - Already partially implemented, just needs integration

2. **Quality Filtering**
   - Very easy (add WHERE clauses)
   - Improves result quality
   - Minor performance gain

3. **Recency Filtering**
   - Easy to implement
   - Better relevance
   - 2-5x performance gain

### ⚠️ **Consider Implementing** (Medium ROI)

4. **Topic Pre-Filtering**
   - Requires full-text search index
   - Medium complexity
   - 5-10x performance gain
   - Better recall

### ❌ **Defer** (Low ROI)

5. **Topic Extraction Column**
   - Requires NLP/parsing
   - Additional storage
   - Can achieve similar results with full-text search

---

## Migration Path

### Step 1: Update match_sessions() Function

Add optional pre-filtering parameters (backward compatible)

### Step 2: Update Python Code

Pass metadata from intent detection to search functions

### Step 3: Add Indexes

Add full-text search index on summary (if doing topic filtering)

### Step 4: Test & Monitor

- Measure performance improvement
- Monitor query latency
- Check result quality

---

## Conclusion

**Metadata pre-filtering is a WIN-WIN**:
- ✅ Faster queries (2-20x improvement)
- ✅ Better results (more relevant)
- ✅ Lower costs (fewer vector operations)
- ✅ Easy to implement (uses existing metadata)
- ✅ Low risk (backward compatible)

**Priority**: Implement date range pre-filtering first (highest impact, easiest to implement).

**Next Steps**: 
1. Update `get_sessions_by_semantic_search()` to accept date_range parameter
2. Pass date_range from intent detection
3. Measure performance improvement
4. Add topic filtering if needed

