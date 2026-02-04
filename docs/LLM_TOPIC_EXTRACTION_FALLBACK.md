# LLM Topic Extraction Fallback

## Overview

The LLM topic extraction uses **Groq Llama 3.1 8B** to extract topics **in parallel** with keyword-based extraction. This ensures we capture both:
- **Known topics** from the vocabulary (via keyword extraction)
- **New topics** not yet in the vocabulary (via LLM extraction, e.g., "jumping", "knitting", "reading")

When enabled, both methods run and results are merged, so you get comprehensive topic coverage for session storage.

## Architecture

```
User Message
    ↓
┌─────────────────────────────────────┐
│  Parallel Extraction (when enabled) │
└─────────────────────────────────────┘
    ↓                    ↓
Keyword Extraction    LLM Extraction
(fast, known topics)  (catches new topics)
    ↓                    ↓
["hobby", "exercise"]  ["jumping", "hobby"]
    ↓                    ↓
    └───────┬───────────┘
            ↓
    Merge & Deduplicate
            ↓
    ["hobby", "exercise", "jumping"] ✅
```

**Note**: When `ENABLE_LLM_TOPIC_FALLBACK=true`, both keyword and LLM extraction run in parallel and results are merged. This ensures we capture both known topics (from vocabulary) and new topics (like "jumping", "knitting") that aren't in the vocabulary yet.

## How It Works

### 1. Primary Path: Keyword Extraction
- Fast (<1ms)
- No API costs
- Uses `WELLNESS_TOPICS` vocabulary
- Handles 95%+ of cases

### 2. Parallel Path: LLM Extraction (when enabled)
- **Runs in parallel with**: Keyword extraction (not just as fallback)
- **Requires**: `ENABLE_LLM_TOPIC_FALLBACK=true` in config
- **Purpose**: Catches new topics not in vocabulary (e.g., "jumping", "knitting", "reading")
- Uses Groq LLM with few-shot examples
- Strict JSON parsing and validation
- Post-processing and canonicalization
- Results are merged with keyword topics (deduplicated)

## Safety Constraints

### JSON Parsing
- LLM must return valid JSON array: `["topic1", "topic2"]`
- Handles cases where LLM adds extra text
- Falls back to empty list if parsing fails

### Post-Processing
- **Lowercase & trim**: All topics normalized
- **Deduplication**: Removes duplicate topics
- **Length limits**: 
  - Min: 2 characters
  - Max: 32 characters per topic
  - Max: 5 topics total
- **Stop word filtering**: Removes common stop words

### Canonicalization
1. **Exact match**: Check against `WELLNESS_TOPICS` vocabulary
2. **Stemming**: Try singularization (e.g., "books" → "book")
3. **Verification**: Keep unknown topics only if they appear verbatim in user text
   - Prevents hallucinations
   - Allows new topics like "reading", "knitting"

### Caching
- In-memory LRU cache (100 entries)
- Keyed by normalized user text hash
- Prevents repeated API calls for same queries

## Configuration

### Enable Fallback

Add to `.env`:
```bash
ENABLE_LLM_TOPIC_FALLBACK=true
```

### Requirements
- `GROQ_API_KEY` must be set
- `LLM_MODEL` must be set (default: `llama-3.3-70b-versatile`)

## Usage

### In Summary Service (Automatic)

The fallback is automatically used in `summary_service.py` when generating session summaries:

```python
# Automatically uses hybrid extraction
topics = await extract_topics_from_user_messages_hybrid(user_messages)
```

### In Intent Detector (Not Used)

**Note**: Intent detector still uses keyword-based extraction only to avoid adding latency to the hot path. This is intentional - intent detection needs to be fast.

## Example Flow

**User says**: "Today, let's talk about new hobby as reading"

1. **Keyword extraction**: Returns `[]` (reading not in vocabulary yet)
2. **LLM fallback** (if enabled):
   - LLM extracts: `["reading", "books", "hobby"]`
   - Post-processing:
     - "reading" → verified in user text → ✅ keep
     - "books" → verified in user text → ✅ keep
     - "hobby" → in vocabulary → ✅ keep
   - Result: `["reading", "books", "hobby"]`

## Monitoring

### Metrics to Track

1. **Fallback trigger rate**: % of sessions where LLM fallback is used
2. **Topic extraction success rate**: % of sessions with topics extracted
3. **LLM API latency**: Average time for LLM topic extraction
4. **Topic quality**: Manual spot checks of extracted topics

### Logs

- `✅ LLM fallback found X topics` - Success
- `LLM topic extraction returned no valid topics` - No topics found
- `Failed to parse JSON from LLM topic extraction` - Parsing error
- `Error in LLM topic extraction` - API error

## Rollout Strategy

### Phase 1: Disabled (Default)
- Feature flag: `ENABLE_LLM_TOPIC_FALLBACK=false`
- All sessions use keyword extraction only
- No changes to existing behavior

### Phase 2: Testing
- Enable for specific users/environments
- Monitor metrics and topic quality
- Collect feedback

### Phase 3: Gradual Rollout
- Enable for 10% of sessions
- Monitor for issues
- Gradually increase to 100%

### Phase 4: Production
- Full rollout
- Monitor continuously
- Adjust prompts/examples as needed

## Troubleshooting

### No Topics Extracted

**Check:**
1. Is `ENABLE_LLM_TOPIC_FALLBACK=true`?
2. Is `GROQ_API_KEY` set?
3. Is `LLM_MODEL` set?
4. Check logs for errors

### Invalid Topics Extracted

**Causes:**
- LLM hallucination (should be filtered by verification)
- JSON parsing failure (should return empty list)
- Post-processing bug

**Fix:**
- Check canonicalization logic
- Review post-processing filters
- Adjust LLM prompt if needed

### High Latency

**Causes:**
- LLM API slow
- Network issues
- Cache misses

**Mitigation:**
- Caching reduces repeated calls
- Consider timeout limits
- Monitor API response times

## Code Locations

- **LLM Extractor**: `backend/bot/services/llm_topic_extractor.py`
- **Hybrid Function**: `backend/bot/services/topic_extractor.py` → `extract_topics_from_user_messages_hybrid()`
- **Usage**: `backend/bot/services/summary_service.py`
- **Config**: `backend/app/core/config.py` → `ENABLE_LLM_TOPIC_FALLBACK`

## Future Improvements

1. **Better Prompting**: Refine few-shot examples based on real usage
2. **Topic Validation**: Add additional validation rules
3. **Performance**: Optimize caching strategy
4. **Monitoring**: Add metrics dashboard
5. **Fine-Tuning**: Eventually replace with fine-tuned SBERT model

