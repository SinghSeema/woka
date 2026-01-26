# Context Loading Review: How Old Context is Fed to the Bot

## Executive Summary

**Current Implementation**: The bot uses a **pre-loading strategy** where past session summaries are fetched **once at session startup** and embedded into the system prompt. There is **NO runtime querying** when users ask specific questions about past conversations.

## Detailed Analysis

### 1. When Context is Loaded

**Location**: `backend/bot/main.py` (lines 84-112)

**Timing**: Context is loaded **once** when the bot joins a room, before the conversation starts.

```python
# Fetch past sessions for agentic memory
past_sessions = []
if settings.SUPABASE_ENABLED:
    past_sessions = await get_past_sessions(user_name, limit=10)
```

**Key Points**:
- ✅ Happens at session initialization
- ✅ Only runs once per session
- ❌ Does NOT query Supabase during conversation
- ❌ Does NOT dynamically fetch additional sessions when asked

### 2. What Data is Loaded

**Source**: `backend/bot/services/database_service.py` (lines 136-199)

**Query Details**:
```python
result = (
    client.table("sessions")
    .select("*")  # Selects ALL columns, but only summaries are used
    .eq("user_name", normalized_name)
    .order("created_at", desc=True)
    .limit(3)  # Only last 10 sessions
    .execute()
)
```

**What Gets Loaded**:
- ✅ Last **10 most recent sessions** only
- ✅ Session summaries (not full transcripts)
- ✅ Metadata: `created_at`, `duration_seconds`, `message_count`
- ❌ **NOT** full conversation transcripts
- ❌ **NOT** sessions beyond the 10 most recent
- ❌ **NOT** any additional data queried at runtime

### 3. How Context is Used

**Location**: `backend/bot/main.py` (lines 164-221)

**Process**:
1. Past sessions are formatted into a text block
2. This text is embedded into the system prompt
3. The system prompt is set once and used throughout the session
4. The LLM uses this static context to answer questions

**System Prompt Structure**:
```
## ROLE
You are "Woka," an empathetic Wellness Coach...

## PAST SESSIONS CONTEXT (Agentic Memory)
[All 10 session summaries formatted here]

## INITIAL TASK
Greet {user_name}...
```

**Key Characteristics**:
- ✅ Context is **static** - doesn't change during conversation
- ✅ All loaded summaries are **always available** to the LLM
- ❌ **Cannot** access sessions beyond the 10 loaded
- ❌ **Cannot** fetch additional context mid-conversation
- ❌ **Cannot** access full transcripts, only summaries

### 4. Runtime Behavior

**What Happens When User Asks About Past Conversations**:

1. User asks: "What did we discuss last time?"
2. **NO database query** is triggered
3. LLM searches through the **pre-loaded summaries** in the system prompt
4. LLM responds based on what was loaded at startup

**Limitations**:
- If user asks about a session older than the 10 most recent → Bot cannot access it
- If user asks for details not in the summary → Bot cannot access full transcript
- If a new session is created during current session → Not available until next session

### 5. Data Flow Diagram

```
Session Start
    ↓
Fetch 10 Most Recent Sessions (Supabase Query #1)
    ↓
Format Summaries into Text
    ↓
Embed into System Prompt
    ↓
Initialize LLM Context (Static)
    ↓
[Conversation Happens - NO MORE QUERIES]
    ↓
User asks about past → LLM searches pre-loaded summaries
    ↓
Session End → Save current session summary (Supabase Query #2)
```

## Comparison: Current vs. Alternative Approaches

### Current Approach: Pre-loading (Static Context)

**Pros**:
- ✅ Fast responses (no database latency)
- ✅ Simple implementation
- ✅ Predictable token usage
- ✅ Works offline after initial load

**Cons**:
- ❌ Limited to 10 most recent sessions
- ❌ Cannot access older sessions
- ❌ Cannot access full transcripts
- ❌ Static context (doesn't update during session)
- ❌ May load unnecessary data if user doesn't ask about past

### Alternative Approach: Runtime Querying (Dynamic Context)

**How it would work**:
- Load minimal context at startup (maybe just 1-2 recent sessions)
- When user asks about past, query Supabase for relevant sessions
- Inject retrieved context into the conversation dynamically

**Pros**:
- ✅ Can access any session, not just recent 10
- ✅ Can query full transcripts when needed
- ✅ More efficient (only load what's needed)
- ✅ Can search by topic/date/keywords

**Cons**:
- ❌ Adds latency to responses
- ❌ More complex implementation
- ❌ Requires query logic and relevance detection
- ❌ May need vector search for semantic queries

## Recommendations

### Option 1: Keep Current Approach (Simple)
**Best for**: Users with < 10 sessions, simple use cases

**Improvements**:
- Increase limit from 10 to 20-30 if token budget allows
- Add configuration for context limit
- Log when user asks about sessions not in context

### Option 2: Hybrid Approach (Recommended)
**Best for**: Production use with many users

**Implementation**:
1. Load 5 most recent summaries at startup (reduced from 10)
2. When user asks about past, detect intent and query Supabase
3. Inject relevant context dynamically into conversation
4. Cache frequently accessed sessions

**Benefits**:
- Faster startup (less data loaded)
- Can access any session when needed
- Better user experience for long-term users

### Option 3: Full Dynamic Approach
**Best for**: Advanced use cases with semantic search

**Implementation**:
- Load minimal context at startup
- Use vector embeddings for semantic search
- Query Supabase with embeddings when user asks about past
- Support queries like "What did we say about sleep?"

## Code Locations

### Key Files:
1. **Context Loading**: `backend/bot/main.py` (lines 84-221)
2. **Database Query**: `backend/bot/services/database_service.py` (lines 136-199)
3. **System Prompt Building**: `backend/bot/main.py` (lines 164-221)
4. **LLM Context**: `backend/bot/main.py` (lines 249-251)

### Key Functions:
- `get_past_sessions()` - Fetches past sessions from Supabase
- `entrypoint()` - Main bot entrypoint that loads context
- System prompt building (inline in `entrypoint()`)

## Current Limitations Summary

1. **Limited History**: Only 10 most recent sessions accessible
2. **No Full Transcripts**: Only summaries available
3. **Static Context**: Cannot update during conversation
4. **No Runtime Querying**: Cannot fetch additional context when asked
5. **No Semantic Search**: Cannot search by topic/keywords
6. **No Date Filtering**: Cannot query sessions by specific date ranges

## Conclusion

The current implementation uses a **pre-loading strategy** that:
- ✅ Loads 10 most recent session summaries at startup
- ✅ Embeds them into the system prompt
- ✅ Makes them available throughout the session
- ❌ Does NOT query Supabase at runtime
- ❌ Does NOT access full transcripts
- ❌ Does NOT access sessions beyond the 10 most recent

This approach is simple and fast but has limitations for users with extensive history or when detailed past context is needed.

