# Shadow Memory & Summarization Implementation

## Overview

This document describes the implementation of **Shadow Memory** (Enhanced Async Cache) and **Semantic Context Compression** strategies to reduce TTFT and overall pipeline latency.

## Implementation Summary

### ✅ Completed Features

1. **Shadow Memory Service** (`backend/bot/services/shadow_memory.py`)
   - Asynchronous pre-warming during handshake
   - Background cache updates after responses
   - Predictive prefetching for common queries
   - Non-blocking operation (doesn't delay pipeline startup)

2. **Filler Generation Service** (`backend/bot/services/filler_generator.py`)
   - Natural filler utterances during cache misses
   - Intent-specific fillers (general, date, topic, semantic)
   - Personalized with user name (30% chance)
   - Hides database query latency (1-2 seconds)

3. **Memory Compression** (`backend/bot/handlers/events.py`)
   - Implemented missing `check_and_summarize_memory()` function
   - Rolling summarization of older messages
   - Keeps recent messages (30) in full detail
   - Compresses older messages into summaries

4. **Integration**
   - Shadow Memory pre-warming in `main.py` entrypoint
   - Filler generation in past reference queries
   - Background cache updates after responses
   - Memory compression monitoring

## Architecture

### Shadow Memory Flow

```
User Joins Room
    ↓
Bot Greets Immediately (no wait)
    ↓ (parallel, non-blocking)
Shadow Memory Pre-warms:
  - Fetch last 5 sessions
  - Cache common queries:
    * "last session"
    * "recent sessions"  
    * "all sessions"
    ↓
User asks about past
    ↓
Check Cache (instant)
    ├─→ Cache Hit: Inject immediately → LLM responds (near-zero latency)
    └─→ Cache Miss:
          ├─→ Generate filler ("Let me check...")
          ├─→ Query DB (async, user already heard filler)
          ├─→ Cache results
          └─→ Inject context → LLM responds
```

### Memory Compression Flow

```
Conversation grows (50+ messages)
    ↓
Monitor checks every turn
    ↓
Threshold reached (every 25 messages after 50)
    ↓
Split messages:
  - Older messages → Summarize
  - Recent 30 messages → Keep full detail
    ↓
Generate summary (background, async)
    ↓
Inject summary into context
    ↓
Remove old messages
    ↓
Continue with compressed context (stable TTFT)
```

## Key Components

### 1. ShadowMemory Class

**Location**: `backend/bot/services/shadow_memory.py`

**Key Methods**:
- `prewarm(limit=5)`: Pre-warms cache with last N sessions
- `update_after_response()`: Updates cache after LLM response
- `_cache_common_queries()`: Caches common query patterns

**Usage**:
```python
shadow_memory = ShadowMemory(context_cache, user_name)
# Pre-warm in background (non-blocking)
asyncio.create_task(shadow_memory.prewarm(limit=5))
```

### 2. Filler Generator

**Location**: `backend/bot/services/filler_generator.py`

**Key Functions**:
- `generate_filler(intent_type, user_name)`: Generates natural filler
- `should_use_filler(query_duration)`: Determines if filler needed

**Example Fillers**:
- General: "Let me check that for you..."
- Date: "Let me look back at those dates..."
- Topic: "Let me search for that topic..."
- Semantic: "Let me think about that..."

### 3. Memory Compression

**Location**: `backend/bot/handlers/events.py` (function: `check_and_summarize_memory()`)

**Key Features**:
- Monitors conversation length and token usage
- Triggers at threshold (50 messages, then every 25)
- Keeps last 30 messages in full detail
- Summarizes older messages into 2-3 sentence summaries
- Injects summaries as system messages

## Configuration

### Settings (in `backend/app/core/config.py`)

```python
# Shadow Memory
ENABLE_DYNAMIC_CONTEXT = True  # Enable Shadow Memory
CONTEXT_CACHE_TTL = 300  # Cache TTL in seconds (5 minutes)

# Memory Compression
ENABLE_CONVERSATION_MEMORY = True
MEMORY_SUMMARIZATION_THRESHOLD = 50  # Messages before compression starts
MEMORY_KEEP_RECENT = 30  # Recent messages to keep in full detail
MEMORY_SUMMARY_FREQUENCY = 25  # Summarize every N messages after threshold
```

## Performance Impact

### Expected Improvements

1. **Cache Hit Rate**: 80-90% of queries hit cache (pre-warmed)
   - **Latency**: Near-zero (cache lookup)
   - **Impact**: Most queries are instant

2. **Cache Miss Rate**: 10-20% of queries miss cache
   - **Latency**: Hidden by filler generation
   - **Impact**: User hears natural filler, doesn't notice delay

3. **Memory Compression**: Prevents context growth
   - **Before**: Context grows linearly (100 messages = ~4000 tokens)
   - **After**: Context stays stable (~2000 tokens regardless of length)
   - **Impact**: Stable TTFT even in long conversations

### Overall Latency Reduction

- **Before**: 500-2000ms per past reference query (DB query on critical path)
- **After**: 
  - Cache hit: ~10ms (cache lookup)
  - Cache miss: ~200-500ms (hidden by filler)
- **Improvement**: 70-80% reduction in perceived latency

## Usage Examples

### Pre-warming Shadow Memory

```python
# In main.py entrypoint
shadow_memory = ShadowMemory(context_cache, user_name)

# Pre-warm in background (non-blocking)
asyncio.create_task(shadow_memory.prewarm(limit=5))
```

### Using Filler Generation

```python
# In event handlers
if cache_miss:
    filler_text = generate_filler(intent.intent_type, user_name)
    await task.queue_frames([LLMMessagesFrame([{
        "role": "assistant",
        "content": filler_text
    }])])
    
    # Now query DB (user already heard filler)
    sessions = await query_database(intent)
```

### Memory Compression

```python
# Automatically triggered in event handlers
# Checks every turn, compresses when threshold reached
await check_and_summarize_memory()
```

## Monitoring

### Logs to Watch

1. **Shadow Memory Pre-warming**:
   ```
   🔥 Pre-warming Shadow Memory for {user}...
   ✅ Shadow Memory pre-warmed: 5 sessions cached in 0.45s
   ```

2. **Cache Hits/Misses**:
   ```
   ✅ Cache hit for query: type:general|query:last session
   ❌ Cache miss for query: type:topic|topics:sleep
   💬 Sent filler: Let me search for that topic...
   ```

3. **Memory Compression**:
   ```
   📊 Memory compression triggered: 75 messages, 3500 tokens
   📝 Compressing memory: 45 messages to summarize, 30 messages to keep
   ✅ Memory compressed: 45 messages removed, summary injected (245 chars)
   ```

## Future Enhancements

### Potential Improvements

1. **Predictive Prefetching**: Analyze user patterns to prefetch likely queries
2. **Cache Hit Rate Tracking**: Monitor and log cache performance
3. **Adaptive Window Size**: Adjust `MEMORY_KEEP_RECENT` based on conversation type
4. **Multi-Tier Caching**: Add Redis for distributed caching across workers

## Notes

- **KV-Caching**: Not implemented (Groq API doesn't support prefix caching)
- **Micro-State Tracking**: Not implemented (can be added for complex workflows)
- **Tool-Calling Pattern**: Not implemented (context injected directly, not via tools)

## Testing

To test Shadow Memory:

1. Start a session
2. Check logs for pre-warming: `🔥 Pre-warming Shadow Memory...`
3. Ask about past sessions (should hit cache)
4. Ask about specific topics (may miss cache, should see filler)
5. Have long conversation (50+ messages) to trigger compression

## Troubleshooting

### Cache Not Pre-warming

- Check `ENABLE_DYNAMIC_CONTEXT` is `True`
- Check `SUPABASE_ENABLED` is `True`
- Check logs for errors during pre-warming

### Memory Not Compressing

- Check `ENABLE_CONVERSATION_MEMORY` is `True`
- Verify message count exceeds threshold (50)
- Check logs for compression triggers

### Fillers Not Appearing

- Verify cache miss is occurring (check logs)
- Check filler generation is called
- Verify `task.queue_frames()` is working

