# Critical Design Flaws - Quick Reference

## 🔴 Critical Issues (Fix Immediately)

### 1. Thread Safety Violations
**Location**: `embedding_service.py`, `context_cache.py`

**Problem**: Global state accessed without locks in async context
- `_embedding_model` (line 16) - race condition on model loading
- `_embedding_cache` (line 19) - no synchronization
- `ContextCache` dicts (line 43-44) - not thread-safe

**Impact**: Crashes, duplicate model loads, memory leaks, data corruption

**Fix**: Add `threading.Lock()` or use `asyncio.Lock()` for async-safe access

---

### 2. Missing Hybrid Intent Detection
**Location**: `intent_detector.py`

**Problem**: Documentation describes hybrid detection (regex + embeddings), but code only implements regex
- Function is synchronous, not async
- No `_detect_with_embeddings()` function exists
- `stt_intent_processor.py` calls it with `await` but function isn't async

**Impact**: Cannot handle edge cases, poor accuracy on paraphrases

**Fix**: Implement async hybrid detection as documented

---

### 3. No Retry Logic for OpenAI API
**Location**: `embedding_service.py` lines 87-139

**Problem**: Single attempt, immediate fallback on any error
- HTTP 429 (rate limit) → immediate fallback
- Network timeouts → immediate fallback
- No exponential backoff
- No distinction between transient vs permanent failures

**Impact**: Unnecessary fallback to local model, poor reliability, wasted API quota

**Fix**: Add retry with exponential backoff, handle 429 specially

---

### 4. Performance Issues: Verbose Logging
**Location**: `database_service.py` lines 156-435

**Problem**: Hundreds of log lines per search at INFO level
- Logs embedding dimensions, norms, means, stds for every item
- Logs similarity scores for all items
- Runs in hot path (every search)

**Impact**: Performance degradation, log storage costs, noise

**Fix**: Move to DEBUG level, reduce verbosity

---

### 5. String Parsing at Search Time
**Location**: `database_service.py` lines 182-231

**Problem**: Embeddings stored as strings are parsed during every search
- Should be parsed once when fetched from DB
- Multiple parsing attempts (JSON, comma-separated)
- No caching of parsed embeddings

**Impact**: Performance degradation, especially with many cached embeddings

**Fix**: Parse embeddings in `get_past_session_embeddings()`, store as lists

---

## 🟡 High Priority Issues

### 6. No Query Timeouts
**Location**: All database query functions

**Problem**: No timeout for Supabase queries
- Could hang indefinitely on slow network
- No cancellation mechanism
- Blocks LLM processing

**Impact**: Poor user experience, resource exhaustion

**Fix**: Add timeout to all async DB operations

---

### 7. Dimension Mismatch Handling
**Location**: `database_service.py` lines 237-243, `embedding_service.py` lines 183-198

**Problem**: Warns but doesn't handle dimension mismatches
- Skips embeddings with wrong dimensions
- No normalization or projection
- No validation that all embeddings use same model

**Impact**: Reduced search quality, silent failures

**Fix**: Validate dimensions on save, normalize vectors, handle mismatches gracefully

---

### 8. Topic Search Inefficiency
**Location**: `database_service.py` lines 1013-1115

**Problem**: Client-side filtering after fetching all sessions
- Fetches `limit * 5` sessions, then filters in Python
- No database-level filtering
- Inefficient for users with many sessions

**Impact**: High memory usage, slow queries, unnecessary DB load

**Fix**: Use database-level filtering, add full-text search indexes

---

### 9. Cache Key Generation Issues
**Location**: `past_context_processor.py` line 188, `context_cache.py` line 250

**Problem**: 
- Uses `hash()` which is not stable across Python runs
- No normalization before hashing
- May miss cache hits for similar queries

**Impact**: Duplicate queries, missed cache hits

**Fix**: Use stable hashing (MD5), normalize text before hashing

---

### 10. Limited Date Range Extraction
**Location**: `intent_detector.py` lines 184-231

**Problem**: Only handles 4 patterns
- No support for absolute dates
- No timezone awareness
- "Last week" assumes Monday-Sunday

**Impact**: Many date queries not detected

**Fix**: Add support for absolute dates, timezone handling, better week calculation

---

## 🟢 Medium Priority Issues

### 11. Hardcoded Confidence Scores
**Location**: `intent_detector.py` lines 76-108

**Problem**: Arbitrary confidence values without context
- Base: 0.5, Date: 0.8, Topic: 0.7, Progress: 0.75
- No consideration of query length, keyword frequency

**Impact**: False positives/negatives with same confidence

**Fix**: Make confidence adaptive based on query characteristics

---

### 12. Basic Topic Extraction
**Location**: `intent_detector.py` lines 126-181

**Problem**: Simple keyword matching
- Hardcoded wellness topics list
- Multiple regex patterns may conflict
- No handling of compound topics

**Impact**: May miss relevant topics or extract incorrect ones

**Fix**: Use NLP for better topic extraction, handle compound topics

---

### 13. Intent Type Logic Issues
**Location**: `intent_detector.py` lines 89-108

**Problem**: Priority conflicts in intent type determination
- Date match sets type, then topic can override
- Logic flow is confusing
- No handling for "progress" with dates/topics

**Impact**: May classify intents incorrectly

**Fix**: Refactor to clear priority logic, handle all combinations

---

### 14. No Input Validation
**Location**: Multiple files

**Problem**: No validation or error handling
- No check for None/empty input
- No handling of malformed patterns
- No logging of detection failures

**Impact**: Silent failures or crashes on edge cases

**Fix**: Add input validation, error handling, logging

---

## Summary Statistics

- **Critical Issues**: 5
- **High Priority**: 5
- **Medium Priority**: 4
- **Total Issues Found**: 14

## Recommended Fix Order

1. Thread safety (Critical #1)
2. Retry logic (Critical #3)
3. Performance: Logging (Critical #4)
4. Performance: Parsing (Critical #5)
5. Query timeouts (High #6)
6. Hybrid detection (Critical #2) - requires more work
7. Dimension handling (High #7)
8. Topic search optimization (High #8)
9. Cache key fixes (High #9)
10. Date range improvements (High #10)

