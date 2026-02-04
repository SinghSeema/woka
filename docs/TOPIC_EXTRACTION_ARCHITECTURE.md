# Topic Extraction Architecture

## Overview

This document describes the hybrid topic extraction and matching system that ensures comprehensive topic coverage while maintaining clean, manageable topic lists in the database.

## Key Principles

1. **Extract topics only when needed**: Query time + session end (not continuously)
2. **Consolidate for storage**: 3-5 high-level topics per session
3. **Semantic matching for queries**: Handle synonyms (e.g., "drawing" → "art")

## Architecture Flow

### 1. Session Storage (Session End)

```
Full Session Transcript
    ↓
Hybrid Topic Extraction
(keyword + LLM parallel)
    ↓
["drawing", "sketching", "painting", "watercolor", "art", "hobby"]
    ↓
LLM Consolidation (3-5 topics)
    ↓
["art", "hobby"] ✅
    ↓
Store in DB
```

**Implementation:**
- `extract_topics_from_user_messages_hybrid()` - Extracts all topics
- `consolidate_topics()` - Consolidates to 3-5 high-level topics
- Called in `summary_service.py` when saving sessions

### 2. Query Time (Past Context Requests)

```
User Query: "what did we discuss about drawing?"
    ↓
Extract Topics from Query Only
(no consolidation)
    ↓
["drawing"]
    ↓
Semantic Topic Matching
(match to stored topics)
    ↓
Query: "drawing" → Stored: "art" (similarity: 0.85)
    ↓
Expanded Topics: ["drawing", "art"]
    ↓
Pre-filter: WHERE topics && ARRAY['drawing', 'art']
    ↓
Semantic Search on Filtered Results
```

**Implementation:**
- `extract_topics_from_query()` - Extracts from query text
- `match_topics_semantically()` - Matches query topics to stored topics
- `_expand_query_topics_with_semantic_matching()` - Expands query topics
- Called in `database_service.py` before pre-filtering

## Components

### Topic Extraction

**Location:** `backend/bot/services/topic_extractor.py`

- `extract_topics_from_user_messages_hybrid()`: Parallel keyword + LLM extraction
- `extract_topics_from_query()`: Query-only extraction (no consolidation)

### Topic Consolidation

**Location:** `backend/bot/services/llm_topic_extractor.py`

- `consolidate_topics()`: Uses LLM to consolidate related topics
  - Input: `["drawing", "sketching", "painting", "watercolor"]`
  - Output: `["art"]`
  - Max: 3-5 topics per session

### Semantic Topic Matching

**Location:** `backend/bot/services/llm_topic_extractor.py`

- `match_topics_semantically()`: Matches query topics to stored topics using embeddings
  - Calculates cosine similarity between topic embeddings
  - Threshold: 0.7 (configurable)
  - Handles synonyms: "drawing" → "art"

**Location:** `backend/bot/services/database_service.py`

- `_expand_query_topics_with_semantic_matching()`: Expands query topics before pre-filtering
  - Gets all stored topics for user
  - Matches query topics semantically
  - Returns expanded list for pre-filtering

## Example Scenarios

### Scenario 1: New Topic Storage

**User says:** "I'm interested in new hobby as drawing modern art"

**Extraction:**
- Keyword: `["hobby"]`
- LLM: `["drawing", "art", "hobby"]`
- Merged: `["drawing", "art", "hobby"]`

**Consolidation:**
- Input: `["drawing", "art", "hobby"]`
- LLM consolidates: `["art", "hobby"]`
- **Stored in DB:** `["art", "hobby"]`

### Scenario 2: Query with Synonym

**User asks:** "what did we discuss about drawing?"

**Query Extraction:**
- Query topics: `["drawing"]`

**Semantic Matching:**
- Stored topics: `["art", "hobby"]`
- Match: "drawing" → "art" (similarity: 0.85)
- Expanded: `["drawing", "art"]`

**Pre-filtering:**
- `WHERE topics && ARRAY['drawing', 'art']`
- Finds session with `["art", "hobby"]` ✅

**Semantic Search:**
- Searches filtered results
- Returns relevant session

### Scenario 3: Long Session

**30-minute session about drawing:**
- User mentions: drawing, sketching, painting, watercolor, canvas, brushes, technique, composition, color theory

**Extraction:**
- Extracts: `["drawing", "sketching", "painting", "watercolor", "canvas", "brushes", "technique", "composition", "color theory", "art", "hobby"]`

**Consolidation:**
- LLM consolidates: `["art", "hobby"]`
- **Stored in DB:** `["art", "hobby"]` (clean, not verbose)

**Query:**
- "what did we discuss about painting?"
- Matches: "painting" → "art" (similarity: 0.88)
- Finds session ✅

## Benefits

1. **Clean Database**: 3-5 topics per session, not 10+
2. **Synonym Handling**: "drawing" query finds "art" sessions
3. **Efficient Pre-filtering**: Semantic matching improves pre-filter accuracy
4. **Comprehensive Coverage**: Parallel extraction catches all topics
5. **Performance**: Topics extracted only when needed

## Configuration

- `ENABLE_LLM_TOPIC_FALLBACK`: Enable LLM extraction (default: `True`)
- Consolidation max topics: 5 (hardcoded, can be made configurable)
- Semantic matching threshold: 0.7 (hardcoded, can be made configurable)

## Future Improvements

1. **Configurable thresholds**: Make consolidation max and similarity threshold configurable
2. **Caching**: Cache topic embeddings for faster semantic matching
3. **Batch matching**: Match multiple query topics in parallel
4. **Topic hierarchy**: Maintain topic relationships (e.g., "drawing" is a type of "art")

