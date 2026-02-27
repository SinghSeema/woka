"""Chunk-question indexing for semantic recall.

Phase 1 changes:
  1. Dual-mode scaffolding detection controlled by SCAFFOLDING_MODE flag:
       "manual"  — heuristic prefix/empathy lists (original logic, zero cost)
       "llm"     — single batched Groq call per session (production grade)
       "both"    — manual first, LLM validates (most accurate)
     ENABLE_MANUAL_SCAFFOLDING = False disables manual detection entirely.
  2. English-only storage: question generation prompt instructs the LLM to
     output English regardless of conversation language. The LLM reads any
     language natively and outputs English. Embedding, dedup, and retrieval
     all remain English-only with no changes.

Three quality gates run before any LLM call is made:

  Gate 1 — Session length guard
      Short sessions (< MIN_USER_MESSAGES_TO_CHUNK real user messages) are
      already captured by the session summary + topics. Chunking them creates
      duplicate, low-quality rows. Skip entirely.

  Gate 2 — Retrieval-session detection
      Sessions where the user is mostly asking about the past ("did we discuss
      X?") are retrieval sessions, not storage sessions. The injected past-
      context responses dominate the transcript — chunking them re-indexes
      history we already have. Detect and skip.

  Gate 3 — Per-chunk worthwhile check
      After chunking, drop any window that landed entirely on recap-injected
      assistant turns (no real user content + all assistants are recaps).

What gets indexed
─────────────────
  chunk_text  — full conversation window (stored for readability/retrieval).

  question generation input — user messages + SUBSTANTIVE assistant responses.
      Assistant scaffolding ("How are you feeling?", "That's great!") is
      stripped ONLY for LLM question generation because:
        • It generates generic questions matching every session
        • It dilutes chunk specificity
      The full chunk_text is still stored in the DB.
"""

import re
import json
from typing import List, Dict, Any, Set

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.embedding_service import generate_embedding
from bot.services.topic_extractor import extract_topics_from_user_messages_hybrid

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Minimum real user messages required before we bother chunking.
# Short single-topic sessions (< this threshold) are already captured by the
# session summary + topics — chunk indexing adds no value and only creates
# duplicate / redundant rows.
MIN_USER_MESSAGES_TO_CHUNK = 6

# Minimum messages a chunk window must contain to be worth indexing.
# The sliding window tail (last 1-2 messages) is almost always just overlap
# from the previous chunk — not a standalone meaningful unit.
# A 2-message chunk like "user: I'm scared. / assistant: [advice]" generates
# 3 questions that duplicate chunks 4 and 5. Require at least 4 messages.
MIN_MESSAGES_PER_CHUNK = 4

# Minimum total chars of non-scaffolding content (user messages + kept assistant
# responses) before generating questions for a chunk. Set above typical
# greeting-only chunks (~75 chars) but below any chunk with real content.
# Also handles request chunks: user asks 3 words, assistant gives 4 methods.
MIN_SUBSTANTIVE_CHARS_FOR_QUESTIONS = 80

# If >= this fraction of assistant messages are past-context recaps, the
# session is a retrieval session (user asking about history) → skip chunking.
RETRIEVAL_SESSION_RECAP_RATIO = 0.6

_PAST_CONTEXT_RECAP_PREFIXES = (
    "in our last session",
    "in our previous session",
    "according to our last session",
    "according to our previous session",
    "let me look for discussions",
    "let me check our past",
    "based on our previous",
    "from our last session",
    "i recall from our last",
    "from our previous conversation",
)

_PAST_CONTEXT_RECAP_PATTERNS = (
    "in our last session,",
    "in our previous session,",
    "from our last session,",
    "we did have a conversation recently",
    "finding sessions about that",
    "let me find our past",
    "searching our past sessions",
)

# Short assistant messages matching these prefixes are conversation scaffolding.
# Stripped from question-generation input only — stored chunk_text is unchanged.
_ASSISTANT_SCAFFOLDING_PREFIXES = (
    "how are you",
    "how are you feeling",
    "how has your",
    "how was your",
    "how did your",
    "did you sleep",
    "did you manage",
    "have you been",
    "have you tried",
    "what would you like to",
    "what would you like",
    "is there anything",
    "shall we",
    "would you like to",
    "are you ready",
    "let's start",
    "let's begin",
    "to summarize,",
    "to recap,",
    "great to hear",
    "that's great",
    "that sounds great",
    "wonderful!",
    "fantastic!",
    "that's wonderful",
    "sounds good",
    "absolutely!",
    "of course!",
    "sure!",
    # Woka-specific patterns seen in real sessions:
    "it sounds like you're getting started",  # filler opener before substantive msg
    "it sounds like you're",                  # short empathy opener
    "that's awesome",                         # short affirmation
    "you've got a great",                     # short affirmation
    "nice to meet you",
    "hello, how can i",
    "hi there",
    "great question",
    "good question",
)

# Scaffolding Category A threshold: messages shorter than this word count are
# treated as short openers/affirmations. Longer messages enter Category B logic
# (checked only if they end with '?').
_SCAFFOLDING_SHORT_WORD_THRESHOLD = 25


# ─────────────────────────────────────────────────────────────────────────────
# Message classification
# ─────────────────────────────────────────────────────────────────────────────

def _is_past_context_recap(content: str) -> bool:
    """Return True if an assistant message is recapping injected past context."""
    lowered = content.lower().strip()
    if any(lowered.startswith(prefix) for prefix in _PAST_CONTEXT_RECAP_PREFIXES):
        return True
    if any(pattern in lowered for pattern in _PAST_CONTEXT_RECAP_PATTERNS):
        return True
    return False


# Markers indicating an assistant message contains real indexable facts.
# Messages with these patterns are KEPT even if they end with a question.
_FACTUAL_CONTENT_PATTERNS = (
    r'\b[1-9]\.\s',                       # numbered list items
    r'\b(google|facebook|youtube|app|website|platform)\b',
    r':\s*\n?\s*[1-9]\.',               # colon then numbered item
    r'\b(step [1-9]|tip [1-9]|option [1-9]|method [1-9])\b',
    r'\b(chlorin|disinfect|sanitat|melatonin|cortisol|serotonin)\b',
    r'\b(calories?|protein|grams?|\bml\b|\bmg\b|\bkg\b)\b',
)

# Words that dominate empathy/motivational scaffolding (no recall value)
_EMPATHY_MARKERS = frozenset([
    'intimidating', 'understandable', 'completely', 'empowerment',
    'confidence', 'motivated', 'altruistic', 'normal', 'worry',
    'supportive', 'exciting', 'fantastic', 'wonderful', 'awesome',
])


def _is_assistant_scaffolding(content: str) -> bool:
    """Return True if an assistant message is scaffolding with no recall value.

    TWO categories are detected:

    Category A — Short openers/affirmations (original logic, kept):
        "Hello, how can I assist you?", "That's great!", "How are you feeling?"
        Detected via prefix list + length cap.

    Category B — Clarification questions (new logic):
        Any message that ends with '?' where the pre-question content is
        empathy/motivation framing rather than indexable facts.
        "Being a beginner can be intimidating... What made you choose swimming?"
        → ends with '?', empathy-dominant, no factual list → STRIP

        Contrast with rich-content messages that also end in '?':
        "Here are 4 methods: 1. Google... 2. Reviews... How do you feel?"
        → ends with '?' but has numbered list → KEEP

    The goal: strip messages the user would never search for.
    Keep messages containing specific facts, recommendations, or data.
    """
    content = content.strip()
    if not content:
        return True

    word_count = len(content.split())

    # ── Category A: short openers/affirmations ────────────────────────────────
    if word_count < _SCAFFOLDING_SHORT_WORD_THRESHOLD:
        # Short enough that it's almost certainly scaffolding
        lowered = content.lower()
        # Any short message ending in '?' is a clarification question
        if content.endswith('?'):
            return True
        # Short affirmations / openers
        if any(lowered.startswith(prefix) for prefix in _ASSISTANT_SCAFFOLDING_PREFIXES):
            return True
        return False

    # ── Category B: clarification questions (longer messages ending in '?') ───
    if not content.endswith('?'):
        return False  # Doesn't end in '?' → not a clarification question

    # Check for factual content markers that justify keeping the message
    for pattern in _FACTUAL_CONTENT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return False  # Has real facts → keep despite ending in '?'

    # Count empathy/motivational words — these signal scaffolding
    empathy_count = sum(1 for w in _EMPATHY_MARKERS if w in content.lower())
    if empathy_count >= 2:
        return True  # Empathy-dominant with no facts → scaffolding

    # ── Category B extended: compound coaching clarification questions ────────
    # Woka's coaching style produces messages like:
    #   "Having consistent energy is helpful for swimming. Now let's talk about
    #    swimming twice a week. To make that a habit, what motivates you to swim
    #    consistently, and what challenges do you think you might face?"
    #
    # These have 3 pre-question sentences (passing the old < 3 check) but the
    # pre-question content is FRAMING, not facts. We detect this pattern:
    #   1. Compound question: final clause contains "and what" or "or what" or
    #      "and how" or "or how" — two open-ended sub-questions joined by and/or
    #   2. Pre-question sentences contain no factual markers
    #
    # If both conditions hold → coaching clarification question → STRIP.
    last_q = re.search(r'[^.!?]*\?$', content)
    if last_q:
        final_clause = last_q.group(0).strip().lower()
        pre = content[:last_q.start()].strip()
        pre_sentences = [s.strip() for s in re.split(r'[.!?]+', pre) if len(s.strip()) > 10]

        # Original volume check — still applies for messages with < 3 pre-sentences
        if len(pre_sentences) < 3:
            return True  # Minimal pre-question content → scaffolding

        # Compound coaching question check (new)
        is_compound_question = bool(re.search(
            r'\b(and|or)\s+(what|how|why|where|when|who|have|do|are|is|can)\b',
            final_clause
        ))

        if is_compound_question:
            # Pre-sentences are framing only if they contain no factual markers
            pre_has_facts = any(
                re.search(p, pre, re.IGNORECASE)
                for p in _FACTUAL_CONTENT_PATTERNS
            )
            if not pre_has_facts:
                return True  # Compound coaching question with no facts → scaffolding

    return False  # Substantive enough to keep


# ─────────────────────────────────────────────────────────────────────────────
# LLM-based scaffolding classification  (SCAFFOLDING_MODE = "llm" or "both")
# ─────────────────────────────────────────────────────────────────────────────

async def _llm_classify_scaffolding(transcript: List[Dict[str, Any]]) -> Set[str]:
    """Classify ALL assistant messages with ONE batched Groq call.

    Returns a set of content strings identified as scaffolding.
    Called ONCE per session before chunking — not per chunk, not per message.

    Cost: ~250 tokens input + ~30 output ≈ $0.0001/session at Groq rates.
    Falls back silently to empty set on any error.
    """
    if not getattr(settings, "GROQ_API_KEY", None):
        return set()

    unique_msgs: List[str] = []
    seen: Set[str] = set()
    for msg in transcript:
        if msg.get("role") == "assistant":
            c = msg.get("content", "").strip()
            if c and c not in seen:
                seen.add(c)
                unique_msgs.append(c)

    if not unique_msgs:
        return set()

    numbered = "\n".join(f"{i}: {msg[:300]}" for i, msg in enumerate(unique_msgs))

    prompt = (
        "Classify each numbered assistant message as scaffolding or substantive.\n\n"
        "SCAFFOLDING (no indexable facts — strip these):\n"
        "  Greetings: 'Hello, how can I assist you?'\n"
        "  Affirmations: 'That's great!', 'Wonderful!'\n"
        "  Clarification questions: 'Are you a beginner or experienced?'\n"
        "  Empathy framing: 'Being a beginner can be intimidating... What made you choose?'\n"
        "  Check-ins: 'How are you feeling?', 'Did you sleep well?'\n\n"
        "SUBSTANTIVE (has indexable facts — keep these):\n"
        "  Numbered recommendations: '1. Google search... 2. Online reviews...'\n"
        "  Named resources, locations, specific techniques\n"
        "  Concrete goals with specifics: 'Aim for 30 min, 3x per week'\n\n"
        "A long message ending in '?' is SCAFFOLDING if pre-question content is "
        "empathy/motivation. It is SUBSTANTIVE if it has a numbered list or specific facts.\n\n"
        f"Messages:\n{numbered}\n\n"
        "Return ONLY a JSON array of INTEGER indices of SCAFFOLDING messages. "
        "Example: [0, 1, 3] means messages 0, 1, 3 are scaffolding. "
        "[] means all are substantive."
    )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.CHUNK_QUESTION_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Classify assistant messages. "
                                "Return ONLY a valid JSON array of integer indices. "
                                "No explanation, no markdown, no extra text."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.0,   # deterministic — classification not generation
                    "max_tokens": 100,    # index list is always small
                },
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"].strip()
            raw = _strip_fences(raw)
            indices = json.loads(raw)

            if not isinstance(indices, list):
                raise ValueError(f"Expected list, got {type(indices).__name__}")

            scaffolding_set: Set[str] = set()
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(unique_msgs):
                    scaffolding_set.add(unique_msgs[idx])

            logger.info(
                f"🤖 LLM scaffolding: {len(scaffolding_set)}/{len(unique_msgs)} "
                f"assistant messages classified as scaffolding"
            )
            return scaffolding_set

    except Exception as e:
        logger.warning(
            f"⚠️  LLM scaffolding failed ({type(e).__name__}: {e}) "
            f"— falling back to manual detection"
        )
        return set()


def _should_strip_as_scaffolding(
    content: str,
    llm_scaffolding_set: Set[str],
) -> bool:
    """Mode-aware scaffolding gate — respects SCAFFOLDING_MODE and ENABLE_MANUAL_SCAFFOLDING.

    mode=manual  → manual heuristic only (if ENABLE_MANUAL_SCAFFOLDING=True)
    mode=llm     → LLM set only. Falls back to manual if LLM call failed (empty set).
    mode=both    → strip if EITHER source flags it (union — most conservative)

    Setting ENABLE_MANUAL_SCAFFOLDING=False disables the manual prefix/empathy
    heuristic in all modes (useful during LLM-only testing to see raw output).
    """
    mode = getattr(settings, "SCAFFOLDING_MODE", "manual").lower()
    manual_enabled = getattr(settings, "ENABLE_MANUAL_SCAFFOLDING", True)

    llm_flag = content.strip() in llm_scaffolding_set

    if mode == "llm":
        if llm_scaffolding_set:      # LLM call succeeded — use its result exclusively
            return llm_flag
        # LLM failed (empty set) — fall back to manual if enabled
        return _is_assistant_scaffolding(content) if manual_enabled else False

    if mode == "both":
        manual_flag = _is_assistant_scaffolding(content) if manual_enabled else False
        return manual_flag or llm_flag

    # mode == "manual" (default)
    if not manual_enabled:
        return False   # Both sources disabled → keep everything
    return _is_assistant_scaffolding(content)


# ─────────────────────────────────────────────────────────────────────────────
# Transcript cleaning
# ─────────────────────────────────────────────────────────────────────────────

def _clean_transcript(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter transcript to real conversation messages only.

    Removes system messages, empty messages, and past-context recap messages.
    Scaffolding messages are kept here — they are only stripped at question-
    generation time via _format_chunk_text_for_questions().
    """
    cleaned = []
    for msg in transcript:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()

        if role not in ("user", "assistant"):
            continue
        if not content:
            continue
        if role == "assistant" and _is_past_context_recap(content):
            logger.debug(f"Skipping recap message: '{content[:80]}'")
            continue

        cleaned.append({"role": role, "content": content})

    return cleaned


def _is_retrieval_session(raw_transcript: List[Dict[str, Any]]) -> bool:
    """Return True if this session is primarily a retrieval (past-asking) session.

    Checks the RAW transcript (before recap removal) to measure what fraction
    of the assistant's responses were past-context recaps. A high ratio means
    the user spent most of the session asking about history — there's no new
    content to chunk and index.

    Uses RETRIEVAL_SESSION_RECAP_RATIO as the threshold.
    """
    assistant_msgs = [
        m for m in raw_transcript
        if m.get("role") == "assistant" and (m.get("content") or "").strip()
    ]
    if not assistant_msgs:
        return False

    recap_count = sum(
        1 for m in assistant_msgs
        if _is_past_context_recap(m.get("content", ""))
    )
    ratio = recap_count / len(assistant_msgs)

    if ratio >= RETRIEVAL_SESSION_RECAP_RATIO:
        logger.info(
            f"⏭️  Retrieval session: {recap_count}/{len(assistant_msgs)} assistant "
            f"msgs are past-context recaps ({ratio:.0%} >= {RETRIEVAL_SESSION_RECAP_RATIO:.0%}). "
            f"No new content to index."
        )
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Chunking
# ─────────────────────────────────────────────────────────────────────────────

def _chunk_transcript(
    messages: List[Dict[str, Any]],
    max_messages: int,
    max_chars: int,
    overlap: int = 2,
) -> List[Dict[str, Any]]:
    """Split cleaned messages into overlapping chunks.

    Sliding window with `overlap` messages carried over so topics that span
    a boundary appear in both adjacent chunks.
    """
    if not messages:
        return []

    chunks: List[Dict[str, Any]] = []
    i = 0
    while i < len(messages):
        window = messages[i : i + max_messages]

        # Trim window to character budget
        current_chars = 0
        trimmed = []
        for msg in window:
            line = f"{msg['role']}: {msg['content']}"
            if trimmed and current_chars + len(line) > max_chars:
                break
            trimmed.append(msg)
            current_chars += len(line)

        if trimmed:
            chunks.append({"messages": trimmed})

        advance = max(1, len(trimmed) - overlap)
        i += advance

    return chunks


def _is_chunk_worthwhile(messages: List[Dict[str, Any]]) -> bool:
    """Return True if the chunk has real content worth indexing.

    Rejects chunks where:
    - Too few messages (sliding window tail — duplicate of previous chunk)
    - No user messages (nothing the user said)
    - All assistant messages are past-context recaps
    """
    # Gate: minimum chunk size. Small tail windows (1-3 messages) are
    # overlap artifacts from the sliding window — they duplicate the
    # previous chunk and generate redundant questions.
    if len(messages) < MIN_MESSAGES_PER_CHUNK:
        return False

    user_messages = [m for m in messages if m.get("role") == "user"]
    if not user_messages:
        return False

    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    if not assistant_messages:
        return True

    recap_count = sum(
        1 for m in assistant_messages
        if _is_past_context_recap(m.get("content", ""))
    )
    return recap_count < len(assistant_messages)


# ─────────────────────────────────────────────────────────────────────────────
# Chunk text formatting — two views
# ─────────────────────────────────────────────────────────────────────────────

def _format_chunk_text(messages: List[Dict[str, Any]]) -> str:
    """Full chunk text for DB storage and retrieval display."""
    return "\n".join(
        f"{m['role']}: {m['content']}"
        for m in messages
        if m.get("content", "").strip()
    )


def _format_chunk_text_for_questions(
    messages: List[Dict[str, Any]],
    llm_scaffolding_set: Set[str] = None,
) -> str:
    """Scaffolding-stripped chunk text sent to the LLM for question generation.

    Removes assistant messages that are pure conversation scaffolding.
    Uses _should_strip_as_scaffolding() which respects SCAFFOLDING_MODE and
    ENABLE_MANUAL_SCAFFOLDING settings.

    If stripping removes everything, the caller falls back to the full text.
    """
    if llm_scaffolding_set is None:
        llm_scaffolding_set = set()

    lines = []
    for m in messages:
        content = (m.get("content") or "").strip()
        if not content:
            continue
        role = m.get("role", "")
        if role == "assistant" and _should_strip_as_scaffolding(content, llm_scaffolding_set):
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Question deduplication and topic resolution
# ─────────────────────────────────────────────────────────────────────────────

def _deduplicate_questions(all_chunk_questions: List[List[str]]) -> List[List[str]]:
    """Remove near-duplicate questions across chunks. First occurrence wins."""
    seen_normalised: Set[str] = set()
    deduplicated: List[List[str]] = []

    for questions in all_chunk_questions:
        unique = []
        for q in questions:
            # Normalise: lowercase, remove punctuation, collapse spaces
            norm = re.sub(r"[^\w\s]", "", q.lower())
            norm = re.sub(r"\s+", " ", norm).strip()

            if norm and norm not in seen_normalised:
                seen_normalised.add(norm)
                unique.append(q)
            else:
                logger.debug(f"Deduplicating: '{q}'")
        deduplicated.append(unique)

    return deduplicated


async def _get_topics_for_chunk(
    chunk_messages: List[Dict[str, Any]],
    session_topics: List[str],
) -> List[str]:
    """Extract topics for a chunk, always merging with session-level topics.

    WHY merge instead of choose:
    A chunk is a window into a session, not a standalone conversation.
    "I'm scared of water infection" (chunk 4) is still part of a swimming
    session — dropping 'swimming' from its topics makes it unreachable
    when the user asks "what did we discuss about swimming?".

    Strategy:
    - Extract chunk-local topics from the chunk's user messages
    - Always UNION with session_topics so session context is never lost
    - Deduplicate and sort for consistency
    """
    user_messages = [
        m.get("content", "") for m in chunk_messages if m.get("role") == "user"
    ]

    chunk_topics: List[str] = []
    if user_messages:
        chunk_topics = await extract_topics_from_user_messages_hybrid(user_messages)

    # Always merge: chunk-local topics + session-level context
    merged = sorted(set(chunk_topics) | set(session_topics))

    if not chunk_topics and session_topics:
        logger.debug("No chunk-local topics — using session topics only")
    elif session_topics:
        added = set(session_topics) - set(chunk_topics)
        if added:
            logger.debug(f"Merged {len(added)} session topics into chunk: {sorted(added)}")

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# JSON parsing — 4-strategy cascade
# ─────────────────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove markdown code fences from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _extract_from_dict(parsed: dict, num_chunks: int, question_count: int) -> List[List[str]]:
    """Pull per-chunk questions from a successfully parsed dict."""
    result = []
    for i in range(1, num_chunks + 1):
        qs = parsed.get(str(i), [])
        result.append([str(q).strip() for q in qs if str(q).strip()][:question_count])
    return result


def _repair_truncated_json(clean: str) -> dict:
    """Try to salvage a truncated JSON object by closing open brackets."""
    last_bracket = clean.rfind("]")
    if last_bracket == -1:
        raise ValueError("No closing bracket found")
    truncated = clean[: last_bracket + 1]
    open_brackets = truncated.count("[") - truncated.count("]")
    open_braces = truncated.count("{") - truncated.count("}")
    repaired = truncated + "]" * max(0, open_brackets) + "}" * max(0, open_braces)
    return json.loads(repaired)


def _regex_extract(raw: str, num_chunks: int, question_count: int) -> List[List[str]]:
    """Boundary-based regex extraction — malformed chunk N never poisons chunk N+1."""
    result = [[] for _ in range(num_chunks)]

    # Find where each "N": key starts in the raw string
    positions = [
        (m.start(), int(m.group(1)))
        for m in re.finditer(r'"(\d+)"\s*:', raw)
        if 1 <= int(m.group(1)) <= num_chunks
    ]
    if not positions:
        return result

    for pos_idx, (start, chunk_num) in enumerate(positions):
        end = positions[pos_idx + 1][0] if pos_idx + 1 < len(positions) else len(raw)
        slice_text = raw[start:end].strip().rstrip(",").strip()

        array_match = re.search(r":\s*\[(.+)", slice_text, re.DOTALL)
        if not array_match:
            continue

        # Extract quoted strings; min 10 chars filters stray chunk-key values like "5"
        questions = re.findall(r'"([^"]{10,300})"', array_match.group(1))
        result[chunk_num - 1] = [q.strip() for q in questions if q.strip()][:question_count]

    return result


def _parse_batched_questions(raw: str, num_chunks: int, question_count: int) -> List[List[str]]:
    """4-strategy cascade: clean parse → repair truncation → regex → empty fallback."""
    if not raw:
        return [[] for _ in range(num_chunks)]

    clean = _strip_fences(raw)

    # Strategy 1: clean parse
    try:

        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            return _extract_from_dict(parsed, num_chunks, question_count)
    except json.JSONDecodeError:
        pass

    # Strategy 2: repair truncated JSON
    try:
        parsed = _repair_truncated_json(clean)
        if isinstance(parsed, dict):
            recovered = sum(1 for i in range(1, num_chunks + 1) if str(i) in parsed)
            logger.info(f"✅ Repaired truncated JSON — recovered {recovered}/{num_chunks} chunks")
            return _extract_from_dict(parsed, num_chunks, question_count)
    except Exception:
        pass

    # Strategy 3: regex extraction
    result = _regex_extract(raw, num_chunks, question_count)
    recovered = sum(1 for r in result if r)
    if recovered > 0:
        logger.info(f"✅ Regex fallback recovered {recovered}/{num_chunks} chunks")
        return result

    logger.warning(f"❌ All parse strategies failed. Raw (first 400): {raw[:400]!r}")
    return [[] for _ in range(num_chunks)]


# ─────────────────────────────────────────────────────────────────────────────
# LLM question generation
# ─────────────────────────────────────────────────────────────────────────────

def _is_vague_question(question: str) -> bool:
    """Return True if a generated question is too vague to be useful for recall.

    Vague questions match every session ("What was the user's goal?") and
    are useless for distinguishing one session from another. We detect them
    by checking for abstract templates that contain no specific named details.

    A question is considered vague when it:
    - Uses "the user" instead of the person's name
    - Asks about generic concepts (goal, feeling, concern) with no specifics
    - Could plausibly be answered by ANY coaching session transcript
    """
    q = question.strip().lower()

    # Patterns that are always vague — no named detail can save them
    always_vague = (
        "what was the user's goal?",
        "what was the user feeling?",
        "what did the user ask for?",
        "what was the user trying to start?",
        "what goal did the user set?",
        "what was the user's concern?",
        "what was the user's plan?",
        "what was the user's challenge?",
        "what was the user's issue?",
        "what was the user struggling with?",
        "what did the user want to achieve?",
        "what was discussed?",
        "what was the main topic?",
    )
    if q in always_vague:
        return True

    # Vague template: "what was the user's [single generic noun]?" with no specifics
    generic_noun_pattern = re.compile(
        r"^what was the user's (goal|feeling|concern|plan|challenge|issue|problem|fear|motivation|reason)\?$"
    )
    if generic_noun_pattern.match(q):
        return True

    return False


def _build_overlap_hint(chunks: List[Dict[str, Any]], question_count: int) -> str:
    """Build a hint string telling the LLM which chunks share overlap content.

    Adjacent chunks in a sliding window share their last N messages with the
    next chunk's first N messages (overlap=2). This causes the LLM to generate
    near-duplicate questions about the same content in both chunks.

    We detect overlap by comparing the first message of chunk N+1 with the
    messages of chunk N. If they share content, we flag it in the hint so
    the LLM knows: "chunk 2 already covers what chunk 1 ends with — don't
    repeat it."

    Returns a one-line instruction string for the prompt.
    """
    if len(chunks) < 2:
        return "assign each question to the chunk where that fact first appears"

    overlap_pairs = []
    for i in range(len(chunks) - 1):
        curr_msgs = {m.get("content", "").strip() for m in chunks[i]["messages"]}
        next_msgs = {m.get("content", "").strip() for m in chunks[i + 1]["messages"]}
        shared = curr_msgs & next_msgs - {""}
        if shared:
            overlap_pairs.append(i + 1)  # 1-indexed chunk number

    if not overlap_pairs:
        return "assign each question to the chunk where that fact first appears"

    overlap_str = ", ".join(f"chunks {n}&{n+1}" for n in overlap_pairs)
    return (
        f"the following share overlap content: {overlap_str}. "
        f"When content appears in both chunks, generate questions about it ONLY in the EARLIER chunk"
    )


async def _generate_questions_for_all_chunks(
    chunks: List[Dict[str, Any]],
    user_name: str,
    llm_scaffolding_set: Set[str] = None,
) -> List[List[str]]:
    """Generate searchable questions for ALL chunks in one batched LLM call.

    Core design principles:
    1. USE THE PERSON'S NAME — "What did Nayna say..." not "What did the user..."
    2. EMBED SPECIFICS IN THE QUESTION — "Why did Nayna say swimming is a
       life-saving skill?" not "What was her motivation?"
    3. VOICE FRAGMENTS — user messages may be incomplete STT fragments; the
       LLM must reconstruct the complete thought before generating questions
    4. NO VAGUE TEMPLATES — "What was the user's goal?" banned explicitly
    5. ENGLISH OUTPUT — questions always in English regardless of conversation language
    6. POST-GENERATION VALIDATION — vague questions filtered after generation
    """
    if llm_scaffolding_set is None:
        llm_scaffolding_set = set()

    if not chunks:
        return []
    if not getattr(settings, "GROQ_API_KEY", None):
        return [[] for _ in chunks]

    question_count = max(1, int(settings.CHUNK_QUESTION_COUNT))

    # Build combined prompt with all chunks numbered
    combined_parts = []
    skip_indices: set = set()  # chunk indices (1-based) with insufficient content
    for i, chunk in enumerate(chunks, 1):
        # Use scaffolding-stripped text — pass llm_scaffolding_set for mode-aware stripping
        q_text = _format_chunk_text_for_questions(chunk["messages"], llm_scaffolding_set)
        if not q_text.strip():
            q_text = _format_chunk_text(chunk["messages"])

        # Measure non-scaffolding content: user messages + kept assistant responses.
        # Count user words only if >= 10 chars (filters pure filler: "So", "Yeah").
        # Count assistant content that survived scaffolding stripping.
        # This correctly handles two real patterns:
        #   a) Greeting-only chunk: user has 75 chars but all greetings → SKIP
        #   b) Request chunk: user asks 2 words, assistant gives 4 methods → GEN
        non_scaffolding_chars = sum(
            len(m.get("content", "").strip())
            for m in chunk["messages"]
            if m.get("role") == "user" and len(m.get("content", "").strip()) >= 10
        ) + sum(
            len(m.get("content", "").strip())
            for m in chunk["messages"]
            if m.get("role") == "assistant"
            and not _should_strip_as_scaffolding(m.get("content", ""), llm_scaffolding_set)
        )
        if non_scaffolding_chars < MIN_SUBSTANTIVE_CHARS_FOR_QUESTIONS:
            skip_indices.add(i)
            logger.debug(
                f"Chunk {i}: only {non_scaffolding_chars} chars of non-scaffolding content "
                f"(min={MIN_SUBSTANTIVE_CHARS_FOR_QUESTIONS}) — skipping question generation"
            )
            combined_parts.append(f"[CHUNK {i}]\n(SKIP — insufficient content)")
        else:
            combined_parts.append(f"[CHUNK {i}]\n{q_text}")
    combined_text = "\n\n".join(combined_parts)

    # user_name for prompt — capitalise for readability
    name = user_name.strip().capitalize() if user_name.strip() else "the user"

    # Build the "already indexed" hint — topics from overlap carry-over chunks
    # The LLM sees all chunks at once, so we tell it upfront what topics each
    # chunk shares with the next to prevent paraphrase redundancy.
    overlap_hint = _build_overlap_hint(chunks, question_count)

    prompt = (
        f"The user's name is {name}. These are chunks from a voice coaching session.\n"
        f"Voice transcripts have sentence fragments (one spoken phrase per line). "
        f"Reconstruct the complete thought across fragments before generating questions.\n\n"
        f"For each numbered chunk, generate {question_count} searchable questions "
        f"that {name} might ask to find THIS specific moment later.\n\n"
        f"STRICT RULES:\n"
        f"1. USE {name.upper()}'S NAME in every question — NEVER write 'the user'\n"
        f"2. EMBED THE SPECIFIC DETAIL — include the actual topic, place, fear, or reason.\n"
        f"   BAD: 'What was {name}'s goal?'  GOOD: 'Why did {name} say swimming is a life-saving skill?'\n"
        f"3. BANNED TEMPLATES — never output: 'What was {name}'s goal/feeling/concern/plan/motivation?'\n"
        f"4. QUESTIONS MUST BE ANSWERABLE FROM USER MESSAGES ONLY.\n"
        f"   Before writing each question, ask yourself: can this be answered by reading ONLY the\n"
        f"   lines starting with 'user:'? If the answer requires reading an 'assistant:' line → DISCARD IT.\n"
        f"   This means: NEVER mirror or paraphrase questions the assistant asked.\n"
        f"   If the user never answered a question the bot posed, do NOT index that question.\n"
        f"5. Each question must be answerable ONLY from its own chunk\n"
        f"6. Questions within a chunk must cover DIFFERENT facts — no paraphrasing each other\n"
        f"7. Adjacent chunks share overlap content — {overlap_hint}\n"
        f"8. OUTPUT IN ENGLISH — always generate questions in English even if the conversation "
        f"was in Hindi, Tamil, or any other language. Embeddings and search are English-only.\n\n"
        f"GOOD examples:\n"
        f"- 'What reason did {name} give for why swimming is important to know?'\n"
        f"- 'What specific health concern did {name} mention about pool water?'\n"
        f"- 'What city did {name} ask for swimming pool recommendations in?'\n"
        f"- 'What was {name}'s experience level with swimming when she started?'\n\n"
        f'Return ONLY valid JSON: {{"1": ["q1", "q2"], "2": ["q1", "q2"], ...}}\n\n'
        f"{combined_text}"
    )

    system_prompt = (
        f"You generate specific recall questions from voice coaching transcripts. "
        f"The user's name is {name}. "
        f"ALWAYS use {name}'s name in questions — never write 'the user'. "
        f"ALWAYS embed the specific named detail in the question itself (hobby name, city, fear, reason). "
        f"NEVER generate: 'What was {name}'s goal/feeling/concern/plan/motivation?' — these are too vague. "
        f"CRITICAL: Every question must be answerable from USER messages only. "
        f"Re-read ONLY the lines starting with 'user:' and ask: can I answer this question from those lines alone? "
        f"If not — if answering requires reading an assistant line — DISCARD that question and generate a different one. "
        f"NEVER mirror or paraphrase questions the assistant asked the user. "
        f"NEVER store what the bot asked — ONLY store what the user said, felt, or wanted. "
        f"The questions must be answerable from USER messages only."
        f"Ask yourself: 'Would {name} type this into a search bar to find this memory?'If not, discard it."
        f"Voice messages are STT fragments — reconstruct the complete thought. "
        f"ALWAYS output questions in English regardless of the conversation language. "
        f"Return ONLY a JSON object mapping chunk numbers (strings) to arrays of questions. "
        f"No markdown, no explanation."
    )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.CHUNK_QUESTION_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,   # Lower → more deterministic, less creative padding
                    "max_tokens": min(2000, max(400, 100 * len(chunks) * question_count)),
                },
            )
            response.raise_for_status()
            result = response.json()
            raw = result["choices"][0]["message"]["content"].strip()
            parsed = _parse_batched_questions(raw, len(chunks), question_count)

            # Post-generation: filter vague questions + enforce skip_indices
            filtered = []
            for chunk_idx, chunk_questions in enumerate(parsed, 1):
                if chunk_idx in skip_indices:
                    filtered.append([])  # No questions for skipped chunks
                    continue
                valid = [q for q in chunk_questions if not _is_vague_question(q)]
                removed = len(chunk_questions) - len(valid)
                if removed:
                    logger.info(f"🧹 Filtered {removed} vague question(s) from chunk {chunk_idx}")
                filtered.append(valid)

            return filtered

    except Exception as e:
        logger.warning(f"Batched chunk question generation failed: {e}")
        return [[] for _ in chunks]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def build_chunk_question_rows(
    transcript: List[Dict[str, Any]],
    user_name: str,
    room_name: str,
    session_topics: List[str] = None,
) -> List[Dict[str, Any]]:
    """Build chunk-question index rows for a completed session.

    Three quality gates:
      Gate 1 — Skip if too few real user messages (< MIN_USER_MESSAGES_TO_CHUNK)
      Gate 2 — Skip if retrieval session (user mostly asked about past history)
      Gate 3 — Drop per-chunk windows that are entirely recap content

    For worthwhile chunks:
      • Store full chunk_text in DB (for retrieval/readability)
      • Strip scaffolding for question generation (for specificity)
      • Deduplicate questions globally
      • Extract topics per chunk
      • Generate embeddings per question
    """
    if not settings.ENABLE_CHUNK_QUESTION_INDEX:
        return []

    session_topics = session_topics or []

    # ── LLM scaffolding pre-classification (runs once if mode requires it) ────
    # This must happen before chunking so the same set is used consistently
    # across all chunks — not re-computed per chunk.
    mode = getattr(settings, "SCAFFOLDING_MODE", "manual").lower()
    llm_scaffolding_set: Set[str] = set()
    if mode in ("llm", "both"):
        llm_scaffolding_set = await _llm_classify_scaffolding(transcript)
        if not llm_scaffolding_set and mode == "llm":
            logger.info(
                "LLM scaffolding returned empty set — manual fallback applies per message"
            )

    # ── Gate 1: Clean + minimum user message count ────────────────────────────
    clean_messages = _clean_transcript(transcript)

    # Step 2: Guard — skip short sessions
    user_message_count = sum(1 for m in clean_messages if m["role"] == "user")

    if user_message_count < MIN_USER_MESSAGES_TO_CHUNK:
        logger.info(
            f"⏭️  Gate 1: {user_message_count} real user messages "
            f"(min={MIN_USER_MESSAGES_TO_CHUNK}). Summary + topics sufficient."
        )
        return []

    # ── Gate 2: Retrieval session detection ───────────────────────────────────
    if _is_retrieval_session(transcript):
        return []

    # ── Chunk the cleaned messages ────────────────────────────────────────────
    chunks = _chunk_transcript(
        clean_messages,
        max_messages=settings.CHUNK_MAX_MESSAGES,
        max_chars=settings.CHUNK_MAX_TEXT_CHARS,
    )

    if not chunks:
        logger.info("No chunks produced after cleaning transcript")
        return []

    # ── Gate 3: Per-chunk worthwhile filter ───────────────────────────────────
    worthwhile_chunks = [c for c in chunks if _is_chunk_worthwhile(c["messages"])]
    skipped = len(chunks) - len(worthwhile_chunks)
    if skipped:
        logger.info(f"⏭️  Gate 3: Dropped {skipped}/{len(chunks)} recap-only chunk windows")
    chunks = worthwhile_chunks

    if not chunks:
        logger.info("No worthwhile chunks after gate 3")
        return []

    logger.info(f"📦 {len(chunks)} worthwhile chunks → question generation")

    # ── Generate questions (1 LLM call, scaffolding-stripped input) ──────────
    all_questions = await _generate_questions_for_all_chunks(
        chunks, user_name, llm_scaffolding_set
    )

    # ── Deduplicate globally ──────────────────────────────────────────────────
    all_questions = _deduplicate_questions(all_questions)
    total_questions = sum(len(qs) for qs in all_questions)
    logger.info(f"✅ {total_questions} unique questions after deduplication")

    # ── Build rows ────────────────────────────────────────────────────────────
    rows: List[Dict[str, Any]] = []
    for idx, (chunk, questions) in enumerate(zip(chunks, all_questions), 1):
        if not questions:
            continue

        chunk_text = _format_chunk_text(chunk["messages"])  # Full text stored
        topics = await _get_topics_for_chunk(chunk["messages"], session_topics)

        for question_text in questions:
            embedding = None
            if settings.ENABLE_SEMANTIC_SEARCH and settings.ENABLE_CHUNK_QUESTION_SEMANTIC_MATCHING:
                embedding = await generate_embedding(question_text)

                # Validate dimension matches schema expectation
                if embedding and len(embedding) != settings.EMBEDDING_DIMENSION:
                    logger.error(
                        f"❌ Embedding dimension mismatch: got {len(embedding)}, "
                        f"expected {settings.EMBEDDING_DIMENSION}. Skipping."
                    )
                    embedding = None

            rows.append({
                "room_name": room_name,
                "user_name": user_name.lower().strip(),
                "chunk_index": idx,
                "question_text": question_text.strip(),
                "chunk_text": chunk_text,
                "topics": topics,
                "question_embedding": embedding,
            })

    logger.info(
        f"✅ Built {len(rows)} chunk-question rows across {len(chunks)} chunks "
        f"for room {room_name}"
    )
    return rows