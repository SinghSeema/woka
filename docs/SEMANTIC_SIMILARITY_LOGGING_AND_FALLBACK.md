# Semantic Similarity Logging and Keyword Search Fallback

## Changes Made

### 1. Enabled Similarity Score Logging ✅

**Changed**: Similarity scores are now logged at **INFO level** (previously DEBUG).

**What's Logged**:
- **Per-item similarity scores**: Each embedding comparison shows:
  - Similarity score (e.g., `0.723`)
  - Threshold (e.g., `0.700`)
  - Match status (✅ MATCH or ❌ below threshold)
  - Summary preview (first 80 chars)

- **Summary statistics**:
  - Max similarity score
  - Min similarity score
  - Average similarity score
  - Number of embeddings checked

- **Top matches**: Top 3 matches with their similarity scores and summaries

**Example Logs**:
```
INFO - Similarity score: 0.723 (threshold: 0.700) - ✅ MATCH | Summary: 'User discussed sleep schedule and nutrition goals...'
INFO - Similarity score: 0.645 (threshold: 0.700) - ❌ below threshold | Summary: 'Session covered exercise routine...'
INFO - ✅ Found 2 semantic matches above threshold 0.700 (max similarity: 0.723, checked 10 embeddings)
INFO -   Match 1: similarity=0.723 | summary='User discussed sleep schedule and nutrition goals...'
INFO -   Match 2: similarity=0.701 | summary='Conversation about wellness and fitness routine...'
```

### 2. Added Keyword Search Fallback ✅

**New Function**: `_fallback_keyword_search()`

**When It's Triggered**:
1. When semantic search finds **no matches** above threshold
2. When query embedding **generation fails**
3. After **all semantic search attempts** fail (local cache + Supabase)

**How It Works**:
1. Extracts keywords from query text (removes stop words)
2. Searches for keywords in session summaries (case-insensitive)
3. Scores sessions by number of keyword matches
4. Returns top matches sorted by score

**Example Flow**:
```
1. Semantic search: No matches above threshold 0.700
2. ❌ No semantic matches found, falling back to keyword search
3. 🔍 Keyword search using: ['singing', 'classes']
4. ✅ Keyword search found 2 sessions (matched keywords: singing, classes)
```

### 3. Fallback Points ✅

Fallback is triggered at multiple points:

1. **After topic-filtered semantic search fails**:
   ```python
   if local_results:
       return local_results
   else:
       # Fallback to keyword search
   ```

2. **After local cache search fails**:
   ```python
   if local_results:
       return local_results
   else:
       # Fallback to keyword search
   ```

3. **After Supabase semantic search fails**:
   ```python
   if sessions:
       return sessions
   else:
       # Fallback to keyword search
   ```

4. **When embedding generation fails**:
   ```python
   if not query_embedding:
       # Fallback to keyword search
   ```

---

## Benefits

### 1. Better Visibility
- **See exactly why** matches were found or not
- **Understand similarity scores** for debugging
- **Track search performance** (max, min, avg scores)

### 2. Improved Reliability
- **Never return empty** when keyword search can find matches
- **Graceful degradation** from semantic → keyword search
- **Works even if embeddings fail** to generate

### 3. Better User Experience
- **Always find relevant sessions** if they exist
- **Fallback ensures** users get results even with low similarity scores
- **Keyword matching** catches cases semantic search misses

---

## Example Scenarios

### Scenario 1: Low Similarity Scores
```
Query: "What did we discuss about singing classes?"

Semantic Search:
- Similarity score: 0.650 (threshold: 0.700) - ❌ below threshold
- Similarity score: 0.620 (threshold: 0.700) - ❌ below threshold
- ❌ No semantic matches found above threshold 0.700 (max: 0.650)

Fallback:
- 🔍 Keyword search using: ['singing', 'classes']
- ✅ Keyword search found 1 session (matched keywords: singing, classes)
```

### Scenario 2: Embedding Generation Fails
```
Query: "What did we talk about last time?"

Embedding Generation:
- ❌ Failed to generate query embedding

Fallback:
- 🔍 Keyword search using: ['talk', 'last', 'time']
- ✅ Keyword search found 3 sessions
```

### Scenario 3: Successful Semantic Match
```
Query: "What did we discuss about sleep?"

Semantic Search:
- Similarity score: 0.823 (threshold: 0.700) - ✅ MATCH
- Similarity score: 0.745 (threshold: 0.700) - ✅ MATCH
- ✅ Found 2 semantic matches above threshold 0.700
-   Match 1: similarity=0.823 | summary='User discussed sleep schedule...'
-   Match 2: similarity=0.745 | summary='Conversation about sleep quality...'
```

---

## Configuration

No configuration needed - logging and fallback are **always enabled**.

**Log Levels**:
- **INFO**: Similarity scores, match results, fallback triggers
- **DEBUG**: Detailed internal operations (unchanged)

---

## Testing

To verify the changes:

1. **Check similarity score logs**:
   - Look for: `"Similarity score: X.XXX (threshold: Y.YYY)"`
   - Should see per-item scores for each embedding comparison

2. **Check fallback triggers**:
   - Look for: `"❌ No semantic matches found, falling back to keyword search"`
   - Should see keyword search results after semantic search fails

3. **Check summary statistics**:
   - Look for: `"max: X.XXX, min: Y.YYY, avg: Z.ZZZ, checked N embeddings"`
   - Should see statistics when no matches found

---

## Notes

- **Performance**: Keyword search is slower than semantic search but ensures results
- **Accuracy**: Keyword search is less accurate but more reliable (catches exact matches)
- **Logging**: INFO level logs are more verbose but provide better debugging
- **Fallback**: Only triggers when semantic search fails, doesn't affect successful searches

