# Topic Storage and Indexing Design

## Overview

Store topics extracted from session summaries in the database and index them for fast topic-based filtering. This enables efficient pre-filtering before expensive vector similarity searches.

---

## Current State

### Problems

1. **Topics Not Stored**: Topics are only extracted during query time (intent detection), not when saving sessions
2. **Inefficient Topic Search**: `get_sessions_by_topic()` does client-side filtering after fetching all sessions
3. **No Topic Indexing**: No database indexes for topic-based queries
4. **Topic Extraction Duplication**: Same logic exists in `intent_detector.py` but not used during summary generation

### Current Flow

```
Session Ends → Generate Summary → Save to DB (no topics)
                                    ↓
Query Time → Extract Topics from Query → Search Summary Text (slow)
```

---

## Proposed Solution

### New Flow

```
Session Ends → Generate Summary → Extract Topics from Summary → Save to DB (with topics + index)
                                    ↓
Query Time → Extract Topics from Query → Filter by Topic Index (fast) → Vector Search (on filtered set)
```

---

## Database Schema Changes

### 1. Add Topics Column

```sql
-- Add topics column as TEXT array
ALTER TABLE sessions ADD COLUMN topics TEXT[];

-- Add comment
COMMENT ON COLUMN sessions.topics IS 'Array of wellness topics discussed in this session (e.g., ["sleep", "nutrition", "exercise"])';
```

### 2. Create GIN Index for Fast Topic Filtering

```sql
-- GIN index for array containment queries
CREATE INDEX idx_sessions_topics_gin 
ON sessions USING gin(topics);

-- This enables fast queries like:
-- WHERE topics @> ARRAY['sleep']  -- Contains 'sleep'
-- WHERE topics && ARRAY['sleep', 'nutrition']  -- Overlaps with any topic
```

**Why GIN Index?**
- Fast array containment queries (`@>` operator)
- Fast array overlap queries (`&&` operator)
- Efficient for multi-topic searches
- Index size: ~20-30% of table size (acceptable)

### 3. Update match_sessions() Function

```sql
CREATE OR REPLACE FUNCTION match_sessions(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    filter_user_name text DEFAULT NULL,
    filter_date_from timestamptz DEFAULT NULL,
    filter_date_to timestamptz DEFAULT NULL,
    filter_topics text[] DEFAULT NULL,  -- NEW
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
        AND (filter_date_from IS NULL OR s.created_at >= filter_date_from)
        AND (filter_date_to IS NULL OR s.created_at <= filter_date_to)
        -- NEW: Topic pre-filtering using GIN index
        AND (
            filter_topics IS NULL OR 
            s.topics && filter_topics  -- Overlaps with any topic (uses GIN index)
        )
        AND s.duration_seconds >= filter_min_duration
        AND (
            filter_date_from IS NOT NULL OR 
            s.created_at >= NOW() - (filter_max_age_days || ' days')::interval
        )
        AND (1 - (s.embedding <=> query_embedding)) >= match_threshold
    ORDER BY s.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

---

## Topic Extraction Function

### Design: Reusable Topic Extractor

Create a shared function that can be used both:
1. **During summary generation** (extract from summary text)
2. **During intent detection** (extract from user query)

**Location**: `backend/bot/services/topic_extractor.py` (new file)

```python
"""Topic extraction service for wellness conversations."""

from typing import List, Set
import re

# Wellness topics vocabulary
WELLNESS_TOPICS = {
    # Sleep & Rest
    'sleep', 'rest', 'insomnia', 'sleeping', 'bedtime', 'wake', 'tired', 'fatigue',
    
    # Nutrition & Diet
    'nutrition', 'diet', 'food', 'eating', 'meal', 'calorie', 'protein', 'carb',
    'vegetable', 'fruit', 'healthy eating', 'meal prep', 'cooking',
    
    # Exercise & Fitness
    'exercise', 'workout', 'fitness', 'training', 'gym', 'running', 'walking',
    'cardio', 'strength', 'yoga', 'stretching', 'movement', 'activity',
    
    # Mental Health
    'stress', 'anxiety', 'mental health', 'depression', 'mood', 'emotion',
    'meditation', 'mindfulness', 'breathing', 'relaxation', 'calm',
    
    # Physical Health
    'pain', 'injury', 'recovery', 'illness', 'symptoms', 'health', 'wellness',
    'energy', 'weight', 'body', 'knee', 'back', 'shoulder', 'joint',
    
    # Habits & Routine
    'habit', 'routine', 'schedule', 'consistency', 'discipline', 'motivation',
    'goal', 'progress', 'achievement', 'challenge', 'struggle',
    
    # Medical
    'doctor', 'treatment', 'medicine', 'medication', 'therapy', 'appointment',
    'diagnosis', 'condition', 'chronic'
}

# Stop words to filter out
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
    'we', 'did', 'do', 'what', 'when', 'where', 'how', 'why', 'about', 'regarding', 'concerning',
    'related', 'discuss', 'discussed', 'talk', 'talked', 'mention', 'mentioned', 'say', 'said',
    'this', 'that', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must',
    'just', 'only', 'also', 'too', 'very', 'much', 'more', 'most', 'some', 'any',
    'past', 'previous', 'before', 'ago', 'last', 'time', 'times', 'session', 'conversation'
}


def extract_topics(text: str, min_confidence: float = 0.5) -> List[str]:
    """Extract wellness topics from text.
    
    Args:
        text: Text to extract topics from (summary, query, etc.)
        min_confidence: Minimum confidence threshold (0.0-1.0)
        
    Returns:
        List of unique topic keywords found in text
    """
    if not text or not text.strip():
        return []
    
    text_lower = text.lower().strip()
    found_topics: Set[str] = set()
    
    # Method 1: Direct vocabulary matching
    for topic in WELLNESS_TOPICS:
        if topic in text_lower:
            found_topics.add(topic)
    
    # Method 2: Extract topics after "about", "regarding", etc.
    about_pattern = r'(?:about|regarding|concerning|related to|discuss|talked about|discussed|focus on|concerning)\s+([a-z\s]+?)(?:\?|\.|,|$)'
    matches = re.finditer(about_pattern, text_lower)
    for match in matches:
        topic_text = match.group(1).strip()
        words = [w for w in topic_text.split() if len(w) > 2]
        # Check if words match known topics
        for word in words:
            if word in WELLNESS_TOPICS:
                found_topics.add(word)
    
    # Method 3: Extract from common patterns
    discuss_pattern = r'(?:discuss|talk|mention|say|cover|address)\s+(?:about\s+)?([a-z\s]+?)(?:\?|\.|,|$)'
    matches = re.finditer(discuss_pattern, text_lower)
    for match in matches:
        topic_text = match.group(1).strip()
        words = [w for w in topic_text.split() if len(w) > 2]
        for word in words:
            if word in WELLNESS_TOPICS:
                found_topics.add(word)
    
    # Filter out stop words
    found_topics = {t for t in found_topics if t not in STOP_WORDS}
    
    # Remove duplicates and sort for consistency
    return sorted(list(found_topics))


def extract_topics_from_summary(summary: str) -> List[str]:
    """Extract topics from session summary.
    
    Optimized for longer summary text (vs short queries).
    
    Args:
        summary: Session summary text
        
    Returns:
        List of topics
    """
    return extract_topics(summary, min_confidence=0.3)


def extract_topics_from_query(query: str) -> List[str]:
    """Extract topics from user query.
    
    Optimized for short query text.
    
    Args:
        query: User query text
        
    Returns:
        List of topics
    """
    return extract_topics(query, min_confidence=0.5)
```

---

## Implementation Plan

### Phase 1: Create Topic Extractor Module

**File**: `backend/bot/services/topic_extractor.py`

- Extract existing topic extraction logic from `intent_detector.py`
- Make it reusable for both summary and query extraction
- Add comprehensive wellness topic vocabulary
- Improve extraction accuracy

### Phase 2: Update Summary Generation

**File**: `backend/bot/services/summary_service.py`

```python
from bot.services.topic_extractor import extract_topics_from_summary

async def generate_session_summary(...) -> Tuple[str, List[str]]:
    """Generate summary and extract topics.
    
    Returns:
        Tuple of (summary_text, topics_list)
    """
    summary = await _generate_llm_summary(...)
    topics = extract_topics_from_summary(summary)
    return summary, topics
```

### Phase 3: Update Database Schema

**Migration Script**: `docs/migrations/add_topics_column.sql`

```sql
-- Add topics column
ALTER TABLE sessions ADD COLUMN topics TEXT[];

-- Create GIN index
CREATE INDEX idx_sessions_topics_gin 
ON sessions USING gin(topics);

-- Update existing sessions (optional - can be done gradually)
-- UPDATE sessions SET topics = extract_topics_from_summary(summary);
```

### Phase 4: Update Save Function

**File**: `backend/bot/services/database_service.py`

```python
async def save_session_summary(
    user_name: str,
    room_name: str,
    summary: str,
    topics: List[str],  # NEW parameter
    duration_seconds: float,
    message_count: int,
) -> bool:
    """Save session summary with topics.
    
    Args:
        topics: List of topics extracted from summary
    """
    data = {
        "room_name": room_name,
        "user_name": normalized_name,
        "summary": summary.strip(),
        "topics": topics,  # NEW: Store topics array
        "duration_seconds": int(duration_seconds),
        "message_count": message_count,
    }
    # ... rest of function
```

### Phase 5: Update Event Handler

**File**: `backend/bot/handlers/events.py`

```python
# Generate summary and topics
summary, topics = await generate_session_summary(
    transcript, user_name, duration,
    performance_monitor=performance_monitor,
    room_name=room_name
)

# Save with topics
success = await save_session_summary(
    user_name=user_name,
    room_name=room_name,
    summary=summary,
    topics=topics,  # NEW
    duration_seconds=duration,
    message_count=message_count,
)
```

### Phase 6: Update Search Functions

**File**: `backend/bot/services/database_service.py`

```python
async def get_sessions_by_topic(
    user_name: str,
    topics: List[str],
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Get sessions by topics using indexed search.
    
    Now uses GIN index for fast array queries.
    """
    normalized_name = user_name.lower().strip()
    
    # Use array overlap operator (&&) - uses GIN index
    result = (
        client.table("sessions")
        .select("*")
        .eq("user_name", normalized_name)
        .contains("topics", topics)  # Supabase array contains
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    
    return result.data if result.data else []
```

### Phase 7: Update Semantic Search

**File**: `backend/bot/services/database_service.py`

```python
async def get_sessions_by_semantic_search(
    user_name: str,
    query_text: str,
    topics: Optional[List[str]] = None,  # NEW
    date_range: Optional[Dict] = None,
    limit: int = 5,
    threshold: float = 0.7,
    ...
):
    """Semantic search with topic pre-filtering."""
    
    # Pre-filter by topics if provided (uses GIN index)
    if topics:
        candidate_sessions = await get_sessions_by_topic(
            user_name, topics, limit=limit * 10
        )
        # Then do vector search on candidates
        return search_cached_embeddings(
            query_embedding,
            candidate_sessions,
            threshold=threshold,
            limit=limit
        )
    # ... rest of function
```

---

## Performance Benefits

### Before (Current)

```
Query: "What did we discuss about sleep?"
  ↓
1. Fetch ALL sessions for user: 100 sessions
2. Client-side filter by "sleep" in summary: 10 sessions
3. Vector search on 10 sessions: 50ms
Total: ~100ms
```

### After (With Topic Indexing)

```
Query: "What did we discuss about sleep?"
  ↓
1. Extract topics: ["sleep"] (1ms)
2. Database filter by topics (GIN index): 10 sessions (2ms)
3. Vector search on 10 sessions: 50ms
Total: ~53ms (1.9x faster)
```

**With 1000 sessions**:
- Before: 1000ms (client-side filtering)
- After: 53ms (indexed filtering)
- **18.9x faster!**

---

## Topic Extraction Quality

### Current Approach (Query-Time)

- Extracts from short user queries
- Limited context
- May miss topics mentioned in summary but not in query

### New Approach (Storage-Time)

- Extracts from full session summary
- More context available
- Better accuracy
- Topics stored once, used many times

### Example

**Summary**: "We discussed sleep schedule, nutrition goals, and exercise routine. User mentioned knee pain during running."

**Extracted Topics**: `["sleep", "nutrition", "exercise", "pain", "knee", "running"]`

**Query**: "What did we say about my knee?"

**Match**: Topic "knee" matches stored topics → Fast indexed lookup → Vector search on filtered set

---

## Migration Strategy

### Option 1: Backfill Existing Sessions

```python
# One-time migration script
async def backfill_topics():
    """Extract and store topics for existing sessions."""
    sessions = await get_all_sessions_without_topics()
    for session in sessions:
        topics = extract_topics_from_summary(session["summary"])
        await update_session_topics(session["id"], topics)
```

**Pros**: All sessions have topics immediately
**Cons**: Requires processing all existing sessions

### Option 2: Lazy Population

```python
# Extract topics on-demand when queried
async def get_sessions_by_topic(user_name, topics):
    # If session has no topics, extract and update
    sessions = await fetch_sessions(user_name)
    for session in sessions:
        if not session.get("topics"):
            topics = extract_topics_from_summary(session["summary"])
            await update_session_topics(session["id"], topics)
            session["topics"] = topics
    # Then filter
```

**Pros**: No upfront cost
**Cons**: First query per session is slower

### Option 3: Hybrid

- New sessions: Extract topics immediately
- Old sessions: Backfill gradually or on-demand

**Recommendation**: Option 3 (hybrid) - best balance

---

## Index Performance

### GIN Index Characteristics

- **Index Size**: ~20-30% of table size
- **Query Speed**: <5ms for topic filtering
- **Insert Overhead**: ~10% slower (acceptable)
- **Maintenance**: Auto-maintained by PostgreSQL

### Query Examples

```sql
-- Fast: Uses GIN index
SELECT * FROM sessions 
WHERE topics @> ARRAY['sleep'];  -- Contains 'sleep'

-- Fast: Uses GIN index
SELECT * FROM sessions 
WHERE topics && ARRAY['sleep', 'nutrition'];  -- Overlaps with any

-- Fast: Uses GIN index
SELECT * FROM sessions 
WHERE 'sleep' = ANY(topics);  -- Alternative syntax
```

---

## Integration with Intent Detection

### Update Intent Detector

**File**: `backend/bot/services/intent_detector.py`

```python
from bot.services.topic_extractor import extract_topics_from_query

def detect_past_reference_intent(user_message: str) -> PastReferenceIntent:
    # ... existing code ...
    
    # Use shared topic extractor
    topics = extract_topics_from_query(user_message)
    
    return PastReferenceIntent(
        has_intent=True,
        intent_type=intent_type,
        topics=topics,  # Now uses shared extractor
        ...
    )
```

**Benefits**:
- Consistent topic extraction
- Single source of truth
- Easier to maintain

---

## Testing Strategy

### Unit Tests

1. **Topic Extraction**
   - Test with various summary texts
   - Test with short queries
   - Test edge cases (no topics, many topics)

2. **Database Operations**
   - Test topic storage
   - Test topic filtering queries
   - Test index usage

### Integration Tests

1. **End-to-End Flow**
   - Generate summary → Extract topics → Save → Query by topic
   - Verify topics are stored correctly
   - Verify topic filtering works

2. **Performance Tests**
   - Measure query time with/without topic filtering
   - Measure index size
   - Measure insert overhead

---

## Rollout Plan

### Step 1: Create Topic Extractor (Low Risk)
- Extract and improve topic extraction logic
- Make it reusable
- Add tests

### Step 2: Add Database Column (Medium Risk)
- Add `topics` column (nullable initially)
- Create GIN index
- Test with sample data

### Step 3: Update Save Function (Low Risk)
- Extract topics during summary generation
- Store topics in database
- Test with new sessions

### Step 4: Update Search Functions (Medium Risk)
- Use topic filtering in searches
- Update `get_sessions_by_topic()`
- Update `get_sessions_by_semantic_search()`

### Step 5: Backfill Existing Sessions (Optional)
- Run migration script
- Or lazy population

### Step 6: Monitor & Optimize
- Monitor query performance
- Monitor index usage
- Optimize topic vocabulary if needed

---

## Future Enhancements

### 1. Topic Confidence Scores

Store topics with confidence scores:
```sql
topics JSONB  -- [{"topic": "sleep", "confidence": 0.9}, ...]
```

### 2. Hierarchical Topics

Organize topics hierarchically:
```sql
topics JSONB  -- {"primary": ["sleep"], "secondary": ["insomnia", "bedtime"]}
```

### 3. LLM-Based Topic Extraction

Use LLM to extract topics (more accurate):
```python
topics = await llm_extract_topics(summary)
```

### 4. Topic Synonyms

Map synonyms to canonical topics:
- "sleeping" → "sleep"
- "workout" → "exercise"

---

## Conclusion

**Topic storage and indexing is a HIGH-VALUE improvement**:

✅ **Fast topic filtering** (2-20x faster queries)
✅ **Better search accuracy** (indexed vs text search)
✅ **Scalable** (GIN index handles large datasets)
✅ **Low risk** (backward compatible)
✅ **Easy to implement** (reuse existing logic)

**Priority**: Implement after date range pre-filtering (similar impact, easier first).

**Next Steps**:
1. Create `topic_extractor.py` module
2. Add `topics` column to database
3. Update summary generation to extract topics
4. Update save function to store topics
5. Update search functions to use topic index

