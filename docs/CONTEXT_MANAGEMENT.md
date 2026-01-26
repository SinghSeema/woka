# Context Management Rules & Guidelines

## Overview

As the project grows, maintaining input context carefully is critical for:
- **Performance**: Avoiding token limit errors and reducing latency
- **Cost**: Minimizing API costs by managing context efficiently
- **Quality**: Ensuring the bot has relevant, prioritized information
- **Scalability**: Supporting long conversations and many past sessions

This document defines rules and best practices for managing context throughout the application.

---

## Table of Contents

1. [Context Components](#context-components)
2. [Token Limits & Budgets](#token-limits--budgets)
3. [System Prompt Rules](#system-prompt-rules)
4. [Past Session Context Rules](#past-session-context-rules)
5. [Conversation History Rules](#conversation-history-rules)
6. [Context Prioritization](#context-prioritization)
7. [Truncation & Summarization Strategies](#truncation--summarization-strategies)
8. [Monitoring & Validation](#monitoring--validation)
9. [Implementation Guidelines](#implementation-guidelines)

---

## Context Components

The bot's context consists of three main components:

### 1. System Prompt
- **Purpose**: Defines bot role, behavior, and capabilities
- **Location**: `backend/bot/main.py` (lines 225-247)
- **Size**: ~500-2000 characters (base)
- **Update Frequency**: Per session (can include user name)

### 2. Past Session Context (Agentic Memory)
- **Purpose**: Provides continuity across sessions
- **Location**: `backend/bot/main.py` (lines 164-221)
- **Size**: Variable (depends on number of sessions)
- **Update Frequency**: Per session (fetched from Supabase)
- **Current Limit**: 10 most recent sessions

### 3. Conversation History
- **Purpose**: Current session messages
- **Location**: Managed by `OpenAILLMContext` in Pipecat
- **Size**: Grows during conversation
- **Update Frequency**: Every message exchange

---

## Token Limits & Budgets

### Model-Specific Limits

| Model | Context Window | Recommended Max | System Prompt Budget | History Budget |
|-------|---------------|----------------|---------------------|----------------|
| `llama-3.3-70b-versatile` | 128K tokens | 100K tokens | 2K tokens | 98K tokens |
| `llama-3.1-8b-instant` | 128K tokens | 100K tokens | 2K tokens | 98K tokens |
| `mixtral-8x7b-32768` | 32K tokens | 25K tokens | 1.5K tokens | 23.5K tokens |

**Note**: Current default is `llama-3.3-70b-versatile` (128K context window)

### Token Budget Allocation

For a typical session with agentic memory:

```
Total Budget: 100K tokens (safety margin from 128K)
├── System Prompt: 2K tokens (2%)
├── Past Session Context: 8K tokens (8%) - 10 sessions
└── Conversation History: 90K tokens (90%)
```

### Token Estimation

- **Characters to Tokens**: ~4 characters per token (English text)
- **System Prompt**: ~500-2000 chars = ~125-500 tokens
- **Past Session Summary**: ~200-400 chars = ~50-100 tokens per session
- **User Message**: ~50-200 chars = ~12-50 tokens
- **Bot Response**: ~100-300 chars = ~25-75 tokens

---

## System Prompt Rules

### Rule 1: Keep Base Prompt Concise
- **Maximum Size**: 2000 characters (500 tokens)
- **Structure**: Use clear sections with headers
- **Avoid**: Redundant instructions, verbose explanations
- **Priority**: Core principles > Style guidelines > Examples

### Rule 2: Dynamic Content Only When Necessary
- **User Name**: Include (personalization is valuable)
- **Past Context**: Include only if past sessions exist
- **Session-Specific Data**: Avoid unless critical

### Rule 3: Prompt Structure Template

```python
system_prompt = f"""
## ROLE
[Concise role definition - 2-3 sentences]

## CORE PRINCIPLES
[Numbered list - 4-6 items max]

## BOUNDARIES & DISCLAIMERS
[Critical safety/scope rules - 3-5 items]

## STYLE & TONE
[Brief style guidelines - 2-3 items]

{past_context if past_context else ""}

## INITIAL TASK
[Single, clear instruction]
"""
```

### Rule 4: Validate Prompt Size
- **Check**: Log prompt size on creation
- **Alert**: Warn if > 2000 characters
- **Action**: Refactor if > 3000 characters

**Implementation**:
```python
prompt_length = len(system_prompt)
if prompt_length > 2000:
    logger.warning(f"System prompt is large: {prompt_length} characters")
if prompt_length > 3000:
    logger.error(f"System prompt exceeds recommended size: {prompt_length} characters")
```

---

## Past Session Context Rules

### Rule 1: Limit Number of Sessions
- **Current Limit**: 10 most recent sessions
- **Rationale**: Balance between context and token usage
- **Configuration**: Set via `limit` parameter in `get_past_sessions()`

**Location**: `backend/bot/main.py` line 92

### Rule 2: Prioritize Recent Sessions
- **Order**: Most recent first (already implemented)
- **Reason**: Recent context is more relevant
- **Future Enhancement**: Consider relevance scoring

### Rule 3: Limit Summary Size Per Session
- **Current**: Full summary from database
- **Recommended**: Max 400 characters per summary
- **Action**: Truncate if summary > 400 characters

**Implementation**:
```python
summary = session.get("summary", "")
if len(summary) > 400:
    summary = summary[:397] + "..."
```

### Rule 4: Calculate Total Past Context Size
- **Target**: < 8000 characters (< 2000 tokens)
- **Check**: Log total size
- **Action**: Reduce session count if exceeds limit

**Implementation**:
```python
past_context_size = len(past_context)
if past_context_size > 8000:
    logger.warning(f"Past context is large: {past_context_size} characters")
    # Consider reducing session count or truncating summaries
```

### Rule 5: Format Past Context Efficiently
- **Use**: Compact formatting (already implemented)
- **Include**: Date, duration, message count, summary
- **Avoid**: Redundant headers, verbose descriptions

### Rule 6: Conditional Inclusion
- **Only Include**: If `past_sessions` list is not empty
- **Check**: Before building context string
- **Log**: Whether past context is included

---

## Conversation History Rules

### Rule 1: Let Framework Manage History
- **Framework**: Pipecat's `OpenAILLMContext` handles history
- **Don't**: Manually manage message history
- **Do**: Trust framework's context window management

### Rule 2: Monitor History Growth
- **Track**: Number of messages in conversation
- **Log**: Periodically (every 10-20 messages)
- **Alert**: If conversation exceeds 100 messages

**Implementation** (if needed):
```python
# In event handlers, track message count
message_count = len(context.messages)
if message_count > 100:
    logger.warning(f"Long conversation: {message_count} messages")
```

### Rule 3: Session Length Limits
- **Recommended**: 30-60 minutes per session
- **Enforcement**: Not required (user can disconnect)
- **Monitoring**: Log session duration

### Rule 4: Handle Context Window Overflow
- **Framework**: Pipecat should handle this automatically
- **Fallback**: If errors occur, implement truncation
- **Strategy**: Keep most recent messages, remove oldest

---

## Context Prioritization

### Priority Order (High to Low)

1. **System Prompt (Core)**: Role, principles, boundaries
2. **System Prompt (Past Context)**: Recent session summaries
3. **Recent Messages**: Last 10-20 messages (most relevant)
4. **Older Messages**: Earlier in conversation
5. **Oldest Past Sessions**: Least recent summaries

### Truncation Strategy

If context exceeds limits, truncate in this order:

1. **Oldest Past Sessions**: Remove sessions beyond limit
2. **Oldest Messages**: Remove oldest conversation messages
3. **Past Session Summaries**: Truncate individual summaries
4. **System Prompt Guidelines**: Remove non-critical guidelines (last resort)

---

## Truncation & Summarization Strategies

### Strategy 1: Past Session Truncation

**When**: Total past context > 8000 characters

**How**:
```python
MAX_PAST_CONTEXT_SIZE = 8000
MAX_SUMMARY_LENGTH = 400

if len(past_context) > MAX_PAST_CONTEXT_SIZE:
    # Reduce number of sessions
    sessions_to_include = min(len(past_sessions), 5)  # Reduce to 5
    # Or truncate summaries
    for session in past_sessions:
        summary = session.get("summary", "")
        if len(summary) > MAX_SUMMARY_LENGTH:
            session["summary"] = summary[:MAX_SUMMARY_LENGTH-3] + "..."
```

### Strategy 2: Summary Compression

**When**: Individual summaries are too long

**How**:
- Truncate to first 400 characters
- Or use LLM to compress (expensive, use sparingly)

### Strategy 3: Conversation History Summarization

**When**: Conversation exceeds 50 messages

**How**:
- Use LLM to summarize older messages
- Keep recent messages (last 20)
- Replace older messages with summary

**Note**: This is advanced and may not be needed with 128K context window.

---

## Monitoring & Validation

### Rule 1: Log Context Sizes

**Location**: `backend/bot/main.py` (already implemented)

**What to Log**:
- System prompt size (characters)
- Past context size (characters)
- Number of past sessions included
- Whether past context is included

**Example** (already implemented):
```python
logger.info(f"✅ System prompt created ({prompt_length} characters)")
logger.info(f"   Includes past session context: {'Yes' if has_past_context else 'No'}")
if has_past_context:
    logger.info(f"   Past context size: {len(past_context)} characters")
```

### Rule 2: Set Warning Thresholds

**Add to code**:
```python
# Warning thresholds
SYSTEM_PROMPT_WARNING = 2000  # characters
SYSTEM_PROMPT_ERROR = 3000    # characters
PAST_CONTEXT_WARNING = 8000   # characters
PAST_CONTEXT_ERROR = 12000    # characters

if prompt_length > SYSTEM_PROMPT_WARNING:
    logger.warning(f"System prompt exceeds warning threshold: {prompt_length} characters")
if len(past_context) > PAST_CONTEXT_WARNING:
    logger.warning(f"Past context exceeds warning threshold: {len(past_context)} characters")
```

### Rule 3: Validate Before Sending to LLM

**Check**:
- Total estimated tokens < model limit
- System prompt + past context < 10K tokens
- Log total context size

### Rule 4: Track Context Usage Over Time

**Metrics to Track**:
- Average system prompt size
- Average past context size
- Average conversation length
- Context overflow events

**Implementation**: Add metrics collection (future enhancement)

---

## Implementation Guidelines

### Guideline 1: Centralize Context Building

**Current**: Context building in `backend/bot/main.py`

**Best Practice**: Create a dedicated function:

```python
def build_system_prompt(
    user_name: str,
    past_sessions: List[Dict],
    settings: Settings
) -> tuple[str, int]:
    """
    Build system prompt with past context.
    
    Returns:
        Tuple of (system_prompt, past_context_size)
    """
    # Implementation here
    pass
```

### Guideline 2: Make Limits Configurable

**Add to `config.py`**:
```python
# Context Management
MAX_PAST_SESSIONS: int = Field(default=10, description="Maximum past sessions to include")
MAX_PAST_CONTEXT_SIZE: int = Field(default=8000, description="Max past context size (characters)")
MAX_SUMMARY_LENGTH: int = Field(default=400, description="Max summary length per session (characters)")
SYSTEM_PROMPT_MAX_SIZE: int = Field(default=2000, description="Max system prompt size (characters)")
```

### Guideline 3: Add Context Validation Function

```python
def validate_context_size(
    system_prompt: str,
    past_context: str,
    model_context_window: int = 128000
) -> tuple[bool, str]:
    """
    Validate context sizes.
    
    Returns:
        Tuple of (is_valid, warning_message)
    """
    # Estimate tokens (rough: 4 chars per token)
    system_tokens = len(system_prompt) // 4
    past_tokens = len(past_context) // 4
    total_tokens = system_tokens + past_tokens
    
    if total_tokens > model_context_window * 0.8:  # 80% of limit
        return False, f"Context exceeds 80% of model limit: {total_tokens} tokens"
    
    if len(system_prompt) > 3000:
        return False, f"System prompt too large: {len(system_prompt)} characters"
    
    if len(past_context) > 12000:
        return False, f"Past context too large: {len(past_context)} characters"
    
    return True, ""
```

### Guideline 4: Document Context Decisions

**When making changes**:
- Document why limits were chosen
- Explain trade-offs
- Update this document

---

## Quick Reference Checklist

### Before Adding New Context

- [ ] Estimate token usage
- [ ] Check if it fits in budget
- [ ] Consider if it's necessary
- [ ] Document the decision

### When Building System Prompt

- [ ] Keep base prompt < 2000 characters
- [ ] Use clear section headers
- [ ] Include only essential instructions
- [ ] Log prompt size

### When Including Past Sessions

- [ ] Limit to 10 sessions (configurable)
- [ ] Truncate summaries > 400 characters
- [ ] Check total past context < 8000 characters
- [ ] Log number of sessions and total size

### When Monitoring

- [ ] Log context sizes on session start
- [ ] Set warning thresholds
- [ ] Monitor for overflow
- [ ] Track metrics over time

---

## Future Enhancements

1. **Relevance Scoring**: Score past sessions by relevance, not just recency
2. **Adaptive Limits**: Adjust session count based on summary sizes
3. **Context Compression**: Use LLM to compress old context
4. **Metrics Dashboard**: Track context usage over time
5. **A/B Testing**: Test different context strategies
6. **User Preferences**: Allow users to control context inclusion

---

## Related Documentation

- [Agentic Memory Guide](AGENTIC_MEMORY.md) - Details on past session management
- [High-Level Design](HLD.md) - Overall architecture
- [Low-Level Design](LLD.md) - Implementation details

---

## Changelog

- **2024-01-XX**: Initial context management rules document created
- **Future**: Update when context management strategies change

---

**Remember**: Context is valuable but expensive. Always prioritize relevance and necessity over completeness.

