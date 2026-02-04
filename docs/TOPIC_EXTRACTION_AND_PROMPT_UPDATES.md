# Topic Extraction and System Prompt Updates

## Changes Made

### 1. Topic Extraction from User Messages Only ✅

**Problem**: Topics were being extracted from session summaries, which include both user queries AND assistant responses. This caused generic topics to be extracted even when the user only asked about specific things (e.g., "zumba" → extracted "cardio", "exercise", "goal", etc.).

**Solution**: Topics are now extracted **ONLY from user messages** in the transcript, not from:
- Session summaries
- Assistant responses
- Combined conversation text

**Implementation**:
- `extract_topics_from_user_messages()` - New function that extracts from user messages only
- Updated `summary_service.py` to extract topics from user messages in transcript
- More strict extraction - only extracts topics explicitly mentioned by the user

### 2. Stricter Topic Extraction ✅

**Problem**: Generic topics like "exercise", "health", "goal" were being extracted even when user only mentioned specific topics.

**Solution**: 
- Added filtering to remove generic topics unless explicitly mentioned
- Generic topics (exercise, health, wellness, goal, etc.) are only included if:
  - User explicitly asks about them (e.g., "about exercise", "regarding health")
  - OR they're the only topic found (user's focus)
- Word boundary matching to prevent partial matches

**Generic Topics Filtered**:
- `health`, `wellness`, `goal`, `progress`, `routine`, `schedule`, `habit`, `lifestyle`
- `fitness`, `exercise`, `workout`, `activity`, `movement`
- `nutrition`, `diet`, `food`, `eating`

**Example**:
- User asks: "What did we discuss about zumba?"
- **Before**: Extracted `["cardio", "exercise", "goal", "gym", "health", "progress", "rest", "routine", "schedule", "weight"]`
- **After**: Extracts `["zumba"]` (or `["zumba", "exercise"]` only if user explicitly mentioned "exercise")

### 3. Added "zumba" to Topic Vocabulary ✅

Added exercise-related topics:
- `zumba`, `dancing`, `dance`, `aerobics`, `pilates`, `crossfit`, `weightlifting`, `lifting`

### 4. Updated System Prompt to Focus on Query ✅

**Problem**: System prompt was too generic and didn't emphasize focusing on the user's specific query.

**Solution**: Updated prompts in:
- `context_injector.py` - Emphasizes focusing on the specific query
- `context_manager.py` - Updated guidelines to be query-focused

**Key Changes**:
- Added: "Focus your answer specifically on what they asked about"
- Added: "Do not provide generic information - be precise and relevant"
- Added: "Only reference information that directly relates to their query"
- Removed: Generic guidance about "tracking progress" and "cross-session patterns" unless relevant

---

## Code Changes

### `topic_extractor.py`

**New Function**:
```python
def extract_topics_from_user_messages(user_messages: List[str]) -> List[str]:
    """Extract topics from user messages only (not from assistant responses)."""
```

**Key Features**:
- Word boundary matching (prevents partial matches)
- Explicit pattern matching (only extracts if user asks "about X")
- Generic topic filtering (removes generic terms unless explicitly mentioned)
- Stricter extraction overall

### `summary_service.py`

**Changed**:
- Now extracts topics from `transcript` user messages, not from `summary` text
- Filters transcript to get only user messages: `[msg for msg in transcript if msg.get("role") == "user"]`

### `context_injector.py`

**Updated Prompt**:
```python
f"**IMPORTANT**: {user_name} asked: \"{query_text}\"\n"
f"Focus your answer specifically on what they asked about. "
f"Use the past session summaries below ONLY to answer their specific question. "
f"Do not provide generic information - be precise and relevant to their query.\n\n"
```

### `context_manager.py`

**Updated Guidelines**:
- Emphasizes focusing on the query
- Warns against generic terms
- Prioritizes precision over breadth

---

## Example: "zumba" Query

### Before

**User asks**: "What did we discuss about zumba?"

**Topics extracted**: 
```json
["cardio", "exercise", "goal", "gym", "health", "progress", "rest", "routine", "schedule", "weight"]
```

**Why**: Summary contained generic wellness terms, extraction matched all of them.

### After

**User asks**: "What did we discuss about zumba?"

**Topics extracted**: 
```json
["zumba"]
```

**Why**: Only extracts from user messages, and "zumba" is the only topic explicitly mentioned.

---

## Testing

To verify the changes work:

1. **Test topic extraction**:
   ```python
   user_messages = ["What did we discuss about zumba?"]
   topics = extract_topics_from_user_messages(user_messages)
   # Should return: ["zumba"] (not generic terms)
   ```

2. **Test with generic topic**:
   ```python
   user_messages = ["I want to talk about exercise"]
   topics = extract_topics_from_user_messages(user_messages)
   # Should return: ["exercise"] (explicitly mentioned)
   ```

3. **Test with multiple specific topics**:
   ```python
   user_messages = ["What did we say about sleep and nutrition?"]
   topics = extract_topics_from_user_messages(user_messages)
   # Should return: ["sleep", "nutrition"] (not "health", "wellness", etc.)
   ```

---

## Migration Notes

**Existing Sessions**: 
- Old sessions may have generic topics stored
- New sessions will have more accurate, query-focused topics
- Consider backfilling old sessions if needed (optional)

**Backward Compatibility**:
- ✅ Code is backward compatible
- ✅ Old sessions without topics still work
- ✅ Topic extraction is more accurate going forward

---

## Benefits

1. **More Accurate Topics**: Only topics user actually asked about
2. **Better Search**: Topic-based search finds more relevant sessions
3. **Focused Responses**: Assistant focuses on user's specific query
4. **Less Noise**: No generic topics cluttering the database

