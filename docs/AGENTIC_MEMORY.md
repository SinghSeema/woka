# Agentic Memory & Session History

## Overview

The Woka Wellness Voice AI Assistant implements **Agentic Memory** - the ability for the bot to remember past conversations and provide continuity across sessions. This is achieved through:

1. **Session Summarization**: Each session is automatically summarized using LLM
2. **Supabase Storage**: Summaries are stored in Supabase (optional)
3. **Context Injection**: Past session summaries are included in the system prompt for new sessions

## Architecture

```
User Session → Transcript (RAM) → LLM Summary → Supabase → Next Session Context
```

## Features

### 1. Automatic Session Summarization

- **Trigger**: When a session ends (user disconnects or call ends)
- **Requirements**: 
  - Minimum 30 seconds duration
  - Minimum 2 messages exchanged
  - Session not already saved
- **Method**: LLM-based summarization using Groq API
- **Content**: Comprehensive summary including:
  - User's goals, concerns, and challenges
  - Topics discussed (sleep, nutrition, exercise, stress, habits)
  - Key advice and recommendations provided
  - User's progress and achievements
  - Plans and next steps
  - User preferences and lifestyle constraints

### 2. Supabase Integration

**Configuration** (in `.env`):
```bash
SUPABASE_ENABLED=true
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

**Table Schema**: See `docs/SUPABASE_SCHEMA.sql`

**Key Features**:
- UUID primary keys for scalability
- User name normalization (lowercase) for consistent lookups
- Room name uniqueness checked in application code
- Automatic timestamps (created_at, updated_at)
- Efficient indexing for fast queries by user_name and created_at
- Row Level Security (RLS) enabled with permissive policy

### 3. Agentic Memory Context

When a user starts a new session:

1. **Retrieval**: Fetches last 10 past sessions from Supabase
2. **Formatting**: Past sessions are formatted with:
   - Session date (readable format)
   - Duration
   - Message count
   - Summary content
3. **Injection**: Formatted context is added to the system prompt
4. **Usage**: Bot uses this context to:
   - Remember user's goals and progress across multiple sessions
   - Reference past conversations naturally
   - Provide continuity and personalized guidance
   - Acknowledge the user's journey
   - **Answer questions about past sessions** (e.g., "What did we discuss last time?")
   - **Share information from multiple past sessions** when relevant
   - **Reference specific sessions by date** when the user asks
   - **Track progress across sessions** and highlight patterns

## Implementation Details

### Summary Generation

**File**: `backend/bot/services/summary_service.py`

- Uses Groq LLM API for summarization
- Optimized prompt for context-rich summaries
- Temperature: 0.4 (balanced creativity/consistency)
- Max tokens: 300 (comprehensive but concise)
- Fallback to basic summary if LLM fails

### Database Operations

**File**: `backend/bot/services/database_service.py`

- Lazy Supabase client initialization
- Input validation before saving
- Error handling and logging
- Efficient queries with indexes

### Context Integration

**File**: `backend/bot/main.py`

- Fetches past sessions on bot startup
- Formats context for system prompt
- Includes guidelines for using past context
- Limits to 10 most recent sessions

## Usage Guidelines

### For the Bot

The bot is instructed to:
- Reference past conversations **naturally** when relevant
- **Answer questions about past sessions** with specific information
- **Reference multiple past sessions** when information spans across sessions
- **Share context from past sessions** when the user asks (e.g., "What was my goal?")
- Acknowledge progress or changes mentioned across sessions
- **Not force connections** - only reference when it adds value or when asked
- Be warm and personal - show you remember their journey
- Use past context to provide continuity
- **Mention specific dates or session numbers** when sharing past information

### For Users

Users can:
- **Ask about past sessions**: "What did we discuss last time?", "What was my goal?", "What did we talk about on [date]?"
- **Reference previous goals**: "How am I doing on my sleep goal?", "Did I mention my exercise routine before?"
- **Ask about progress**: "What progress have I made?", "What did we discuss about my nutrition?"
- **Request information from multiple sessions**: The bot can reference and combine information from multiple past sessions
- **Expect continuity**: The bot remembers their journey across all past sessions
- **Get specific details**: The bot can share specific information, dates, and context from past conversations

## Privacy & Security

- **User Name Normalization**: Names are normalized (lowercase) for consistent lookups
- **No Personal Data**: Only summaries are stored, not full transcripts
- **Optional**: Supabase integration can be disabled
- **RLS Ready**: Schema supports Row Level Security if needed

## Troubleshooting

### Summaries Not Saving

1. Check `SUPABASE_ENABLED=true` in `.env`
2. Verify `SUPABASE_URL` and `SUPABASE_KEY` are correct
3. Check bot logs for errors
4. Ensure session meets minimum requirements (30s, 2 messages)
5. Verify Supabase table exists (run `SUPABASE_SCHEMA.sql`)

### Past Sessions Not Loading

1. Check Supabase connection in logs
2. Verify user name normalization matches
3. Check if sessions exist in Supabase dashboard
4. Review error logs for query issues

### Poor Context Quality

1. Check summary quality in Supabase
2. Review summary generation logs
3. Adjust LLM parameters if needed
4. Ensure sufficient conversation content

## Future Enhancements

- [ ] Semantic search for relevant past sessions
- [ ] Session clustering by topics
- [ ] Progress tracking and analytics
- [ ] User-specific memory preferences
- [ ] Export/import session history
- [ ] Multi-user support with authentication

