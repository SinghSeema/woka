# Hierarchical Storage Approach - Design Discussion

## Problem Statement

**Current Issue**: Low cosine similarity scores when comparing short, specific queries ("My knee hurts") against long, general session summaries ("We discussed diet, sleep, and knee pain over 20 minutes").

**Root Cause**: Sentence transformers are optimized for single thoughts. A session summary embedding is an "average" of multiple topics, making it semantically "blurry" compared to specific queries.

---

## Proposed Solution: Hierarchical Storage

### Architecture

```
Level 1: Session Summary (General Context)
  - One embedding per session
  - Broad, high-level context
  - Used for: "What did we discuss?", "How am I doing?"

Level 2: Message Pairs (Specific Context)
  - One embedding per user-assistant exchange
  - Specific, focused conversations
  - Used for: "My knee hurts", "What did you say about sleep?"
```

### Storage Structure

```python
# Session Level (existing)
{
    "session_id": "uuid",
    "summary": "We discussed diet, sleep, and knee pain...",
    "summary_embedding": [0.1, 0.2, ...],
    "created_at": "2024-01-15",
    "message_pairs": [...]  # NEW
}

# Message Pair Level (new)
{
    "pair_id": "uuid",
    "session_id": "uuid",
    "user_message": "My knee hurts when I run",
    "assistant_message": "Let's check your running form...",
    "pair_text": "User: My knee hurts when I run\nAssistant: Let's check your running form...",
    "pair_embedding": [0.3, 0.4, ...],  # More specific vector
    "timestamp": "2024-01-15T10:30:00"
}
```

---

## Analysis: Pros and Cons

### ✅ Advantages

#### 1. **Higher Similarity Scores**
- **Specific queries match specific pairs**: "My knee hurts" → matches "User: My knee hurts when I run"
- **Expected similarity**: 0.7-0.9 (vs current 0.3-0.5)
- **Better recall**: More relevant results surface

#### 2. **Better Query Understanding**
- Short queries ("knee", "sleep") naturally match focused message pairs
- No need to parse complex summaries
- Semantic alignment between query and stored content

#### 3. **Granular Context**
- Can retrieve exact conversation snippets
- More precise context injection
- Better for specific follow-up questions

#### 4. **Progressive Fallback**
```
Query: "My knee hurts"
  ↓
Search message pairs (high similarity expected)
  ↓
If no good matches → Search session summaries (broader context)
  ↓
If still no matches → Return most recent sessions
```

### ❌ Challenges

#### 1. **Storage Overhead** (CRITICAL)

**Current**: 
- 1 embedding per session
- ~384 dimensions (local model) or 1536 (OpenAI)
- ~1.5KB per session

**Proposed**:
- 1 embedding per session + N embeddings per message pair
- Average session: 20-50 message pairs
- **20-50x storage increase**

**Example Calculation**:
```
100 sessions × 30 pairs/session = 3,000 embeddings
3,000 × 1.5KB = 4.5MB (just embeddings)
+ Text storage for each pair
+ Database indexes
= ~10-20MB per 100 sessions (vs current ~150KB)
```

**Impact**:
- Database size grows 50-100x
- Storage costs increase significantly
- Query performance may degrade with more vectors

#### 2. **Database Schema Changes**

**New Table Required**:
```sql
CREATE TABLE message_pairs (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    user_message TEXT,
    assistant_message TEXT,
    pair_text TEXT,  -- Combined for embedding
    embedding vector(384),
    timestamp TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_message_pairs_session ON message_pairs(session_id);
CREATE INDEX idx_message_pairs_embedding ON message_pairs USING ivfflat (embedding vector_cosine_ops);
```

**Migration Required**:
- Existing sessions won't have message pairs
- Need to decide: backfill or start fresh?
- Schema versioning complexity

#### 3. **Embedding Generation Cost**

**Current**:
- 1 embedding per session (at session end)
- ~10-50ms per embedding
- Total: ~50ms per session

**Proposed**:
- 1 embedding per session + N per message pair
- 30 pairs × 50ms = 1.5 seconds per session
- **30x slower** session save time
- More API calls (if using OpenAI)

**Cost Implications** (OpenAI):
- Current: $0.0001 per session (1 embedding)
- Proposed: $0.003 per session (30 embeddings)
- **30x cost increase**

#### 4. **Query Performance**

**Current**:
- Search ~100 session embeddings
- Fast: <10ms with local cache

**Proposed**:
- Search ~3,000 message pair embeddings
- Slower: 50-100ms even with indexing
- Need efficient vector search (pgvector with HNSW)

**Mitigation**:
- Two-stage search: pairs first, then summaries
- Limit search scope (recent sessions only)
- Use approximate nearest neighbor (ANN) indexes

#### 5. **Context Injection Complexity**

**Current**:
- Inject full session summaries
- Simple, coherent context

**Proposed**:
- If message pair match: inject just that pair? Or full session?
- How to combine multiple pair matches?
- Risk of fragmented, incoherent context

**Example Problem**:
```
Query: "What did we discuss about my health?"
Matches:
  - Pair 1: "User: My knee hurts" → "Assistant: Check form"
  - Pair 2: "User: I'm sleeping poorly" → "Assistant: Try meditation"
  - Pair 3: "User: My diet is bad" → "Assistant: Start meal prep"

Injected context: 3 disconnected snippets
vs
Current: One coherent summary of all topics
```

#### 6. **Message Pair Definition**

**Questions**:
- What constitutes a "pair"? User message + next assistant response?
- What if user sends multiple messages before assistant responds?
- What if assistant sends multiple messages?
- How to handle system messages, errors, interruptions?

**Edge Cases**:
```
User: "My knee hurts"
User: "Especially when running"
Assistant: "Let's check your form"
→ One pair or two?
```

#### 7. **Transcript Storage**

**Current**:
- Transcript stored in memory during session
- Discarded after summary generation
- Not persisted to database

**Proposed**:
- Need to persist full transcript
- Store message pairs in database
- More data to manage, backup, migrate

---

## Hybrid Approach: Best of Both Worlds?

### Option A: Smart Pair Selection

Instead of embedding ALL message pairs, only embed "significant" ones:

**Criteria for Significant Pairs**:
- User message length > 10 words
- Assistant response length > 20 words
- Contains keywords (goals, concerns, advice, plans)
- User asks a question
- Assistant provides specific advice

**Benefits**:
- Reduces storage by 50-70%
- Focuses on meaningful exchanges
- Still provides granular matching

**Challenges**:
- Need to define "significant" algorithmically
- Risk of missing important context
- More complex logic

### Option B: Two-Phase Search

**Phase 1**: Search message pairs (if available)
- Fast, specific matches
- Return top 3-5 pairs

**Phase 2**: If Phase 1 finds matches, fetch parent session summaries
- Provides broader context
- Ensures coherence

**Benefits**:
- Best of both: specific + general
- Progressive enhancement
- Backward compatible (sessions without pairs still work)

### Option C: Query-Aware Routing

**Route queries based on specificity**:

```
Short, specific query ("knee hurts")
  → Search message pairs only
  → High similarity expected

Long, general query ("What did we discuss?")
  → Search session summaries only
  → Better semantic match

Mixed query ("What did we say about my knee?")
  → Search both, combine results
```

**Benefits**:
- Optimize for query type
- Reduce unnecessary searches
- Better performance

**Challenges**:
- Need to classify query specificity
- More complex routing logic

---

## Implementation Considerations

### 1. **When to Generate Pair Embeddings?**

**Option A: During Session (Real-time)**
- Generate embedding after each user-assistant exchange
- Pros: No delay at session end
- Cons: More API calls, potential failures mid-session

**Option B: At Session End (Batch)**
- Generate all pair embeddings when session ends
- Pros: Single batch operation, easier error handling
- Cons: Slower session save, user waits

**Option C: Lazy (On-Demand)**
- Generate embeddings when first queried
- Pros: No upfront cost
- Cons: First query is slow, complexity

**Recommendation**: Option B (batch at session end) - most reliable

### 2. **Storage Strategy**

**Option A: Separate Table**
- `message_pairs` table with foreign key to `sessions`
- Pros: Clean separation, easy queries
- Cons: More joins, more complex queries

**Option B: JSON Column**
- Store pairs as JSON array in `sessions` table
- Pros: Simple, no joins
- Cons: Harder to query, less efficient

**Option C: Hybrid**
- Store pairs in separate table
- Cache in session row for fast access
- Pros: Best of both
- Cons: Data consistency complexity

**Recommendation**: Option A (separate table) - most scalable

### 3. **Search Strategy**

**Current Flow**:
```
Query → Generate embedding → Search sessions → Return summaries
```

**Proposed Flow**:
```
Query → Generate embedding
  ↓
Search message pairs (limit: 10, threshold: 0.7)
  ↓
If matches found:
  - Group by session_id
  - Fetch parent session summaries
  - Combine: pairs + summaries
  ↓
If no matches:
  - Search session summaries (fallback)
  ↓
Return results
```

### 4. **Context Injection Strategy**

**If Message Pair Match**:
```python
# Option 1: Inject pair + parent summary
context = f"""
Session from {date}:
{parent_session_summary}

Relevant exchange:
User: {pair.user_message}
Assistant: {pair.assistant_message}
"""

# Option 2: Inject only pair (more focused)
context = f"""
From session on {date}:
User: {pair.user_message}
Assistant: {pair.assistant_message}
"""

# Option 3: Inject multiple pairs + summary
context = f"""
Session from {date}:
{parent_session_summary}

Key exchanges:
{pair1}
{pair2}
{pair3}
"""
```

**Recommendation**: Option 1 (pair + summary) - provides context without losing coherence

---

## Performance Impact Analysis

### Storage Growth

| Metric | Current | Proposed | Increase |
|--------|---------|----------|----------|
| Embeddings per session | 1 | 30 | 30x |
| Storage per session | 1.5KB | 45KB | 30x |
| 100 sessions | 150KB | 4.5MB | 30x |
| 1000 sessions | 1.5MB | 45MB | 30x |

### Query Performance

| Operation | Current | Proposed | Impact |
|-----------|---------|----------|--------|
| Local cache search | <1ms | 5-10ms | 5-10x slower |
| Supabase vector search | 50-100ms | 200-500ms | 2-5x slower |
| Embedding generation | 50ms | 1.5s | 30x slower |

### Cost (OpenAI Embeddings)

| Metric | Current | Proposed | Increase |
|--------|---------|----------|----------|
| Embeddings per session | 1 | 30 | 30x |
| Cost per session | $0.0001 | $0.003 | 30x |
| 1000 sessions/month | $0.10 | $3.00 | 30x |

---

## Recommendation: Phased Approach

### Phase 1: Proof of Concept (Low Risk)

**Scope**: 
- Add message pair storage (optional, not required)
- Generate embeddings for recent sessions only (last 10)
- Test with small dataset

**Goals**:
- Validate similarity improvement
- Measure actual performance impact
- Test context injection quality

**Success Criteria**:
- Similarity scores improve by 20%+
- Query latency < 200ms
- Context quality maintained or improved

### Phase 2: Selective Implementation (Medium Risk)

**Scope**:
- Implement smart pair selection (only significant pairs)
- Two-phase search (pairs first, then summaries)
- Query-aware routing

**Goals**:
- Reduce storage overhead by 50%
- Maintain performance
- Improve search quality

### Phase 3: Full Implementation (If Phase 2 Succeeds)

**Scope**:
- Full hierarchical storage
- All message pairs embedded
- Optimized indexes and caching

**Goals**:
- Production-ready system
- Scalable to thousands of sessions
- Cost-effective

---

## Alternative: Improve Current System First

Before implementing hierarchical storage, consider:

### 1. **Better Summary Generation**
- Use more focused prompts
- Generate topic-specific summaries
- Create multiple summaries per session (one per major topic)

### 2. **Query Expansion**
- Expand short queries before embedding
- "knee" → "knee pain knee injury running form"
- Improves matching without storage overhead

### 3. **Hybrid Search**
- Combine semantic search with keyword search
- Use BM25 for exact matches, embeddings for semantic
- Better recall without storage increase

### 4. **Threshold Tuning**
- Lower similarity threshold for short queries
- Adaptive thresholds based on query length
- Simple fix, no architecture changes

---

## Decision Framework

### Choose Hierarchical Storage If:
- ✅ Similarity scores are consistently low (<0.5)
- ✅ Users frequently ask specific questions
- ✅ Storage costs are acceptable (30x increase)
- ✅ Query latency increase is acceptable (2-5x)
- ✅ You have resources for schema migration

### Choose Alternative Approaches If:
- ❌ Storage costs are a concern
- ❌ Query latency must stay <100ms
- ❌ Current system works "well enough"
- ❌ Resources are limited
- ❌ You want to validate improvement first

---

## Open Questions for Discussion

1. **Storage Budget**: Is 30x storage increase acceptable?
2. **Performance**: Is 2-5x query latency acceptable?
3. **Cost**: Is 30x embedding cost acceptable?
4. **Migration**: How to handle existing sessions?
5. **Pair Definition**: What exactly is a "message pair"?
6. **Context Injection**: How to combine pairs and summaries?
7. **Fallback**: What if pair search finds nothing?
8. **Indexing**: Which vector index to use (HNSW, IVFFlat)?
9. **Caching**: How to cache 3000+ embeddings efficiently?
10. **Testing**: How to validate improvement?

---

## Next Steps

1. **Measure Current Performance**
   - Collect similarity scores for real queries
   - Identify patterns (what queries fail?)
   - Baseline metrics

2. **Prototype Message Pair Storage**
   - Add `message_pairs` table
   - Generate embeddings for 10 test sessions
   - Compare similarity scores

3. **Benchmark Performance**
   - Measure query latency
   - Measure storage growth
   - Measure embedding generation time

4. **Test Context Quality**
   - A/B test: pairs vs summaries
   - User feedback on response quality
   - Coherence analysis

5. **Make Decision**
   - Based on data, not assumptions
   - Consider alternatives
   - Plan implementation

---

## Conclusion

The hierarchical storage approach addresses a real problem (low similarity scores) but introduces significant complexity and cost. 

**Key Trade-offs**:
- ✅ Better similarity scores
- ❌ 30x storage increase
- ❌ 30x embedding cost
- ❌ 2-5x query latency
- ❌ Complex implementation

**Recommendation**: Start with Phase 1 (proof of concept) to validate the approach before committing to full implementation. Consider alternative approaches (query expansion, better summaries) that may provide 80% of the benefit with 20% of the cost.

