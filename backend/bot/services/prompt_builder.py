"""System prompt building service for the bot.

Phase 2: build_base_system_prompt() accepts an optional language_code.
For non-English sessions it adds a LANGUAGE section that tells the LLM:
  - What language the user is speaking in
  - That it can understand the user's language
  - That it should respond in English (because Deepgram TTS is English-only)
  - That session memory is handled in English internally

Storage (chunk question index, summaries) stays English throughout — 
that was handled in Phase 1 and is not affected by this change.
"""

import sys
from pathlib import Path
from typing import Dict, Optional

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.context_manager import estimate_tokens
from bot.services.language_config import (
    get_display_name,
    is_english,
    normalise_language_code,
    DEFAULT_LANGUAGE,
)

logger = get_logger(__name__)


def _extract_commitments_from_summary(summary: str) -> Optional[str]:
    """Pull the COMMITMENTS field out of a structured summary string.

    Returns the commitments text, or None if absent / "none".
    """
    import re
    match = re.search(r"^COMMITMENTS:\s*(.+)$", summary, re.IGNORECASE | re.MULTILINE)
    if match:
        value = match.group(1).strip()
        if value.lower() not in ("none", "n/a", "-", ""):
            return value
    return None


def build_base_system_prompt(
    user_name: str,
    bot_name: Optional[str] = None,
    language_code: Optional[str] = None,
    previous_session_summary: Optional[str] = None,
    previous_session_metadata: Optional[Dict[str, str]] = None,
) -> str:
    """Build the base system prompt for the bot.

    Args:
        user_name:                 Name of the user for personalisation.
        bot_name:                  Name of the bot (defaults to settings.BOT_NAME).
        language_code:             BCP-47 session language (e.g. "hi", "ta", "en").
                                   Defaults to settings.SESSION_LANGUAGE or "en".
        previous_session_summary:  Structured summary text from the last session (in-memory
                                   format). COMMITMENTS field parsed via regex if provided.
        previous_session_metadata: Metadata dict from the DB sessions.metadata column.
                                   Takes precedence over previous_session_summary for
                                   commitment extraction when both are present.

    Returns:
        Base system prompt string.
    """
    if bot_name is None:
        bot_name = settings.BOT_NAME

    raw_code = (
        language_code
        or getattr(settings, "SESSION_LANGUAGE", None)
        or DEFAULT_LANGUAGE
    )
    lang_key = normalise_language_code(raw_code)
    display_name = get_display_name(lang_key)
    non_english = not is_english(lang_key)

    prompt = f"""## ROLE
You are "{bot_name}," an empathetic, professional, and motivational Wellness Coach. Your goal is to help {user_name} achieve their health goals through lifestyle, habit formation, and positive mindset shifts.

## CORE PRINCIPLES
1. **Scope of Practice:** You provide advice on nutrition, exercise, sleep, and stress management. 
2. **Safety First:** You are NOT a doctor, therapist, or medical professional. 
3. **Guardrails:** If {user_name} asks for medical diagnoses, prescriptions, or advice on chronic illnesses/injuries, you must refuse and redirect to a professional.
4. **Ethics:** Never encourage extreme diets, self-harm, or dangerous physical activities. If a request is "wrong" or potentially harmful, politely decline.

## BOUNDARIES & DISCLAIMERS
- **Mandatory Disclaimer:** If a user asks about a health condition, start with: "I'm here to support your wellness journey, but I'm not a medical professional. Please consult a doctor for medical concerns."
- **Refusal Protocol:** If the user asks something outside your scope or unethical, say: "I'm focused on wellness coaching (habits, movement, and mindset). I cannot provide advice on [Topic], as that falls outside my expertise."

## STYLE & TONE
- **Tone:** Grounded, encouraging, and clear.
- **Style:** Keep responses concise — this is a voice conversation, not a text chat.
- **Greeting:** Start by warmly greeting {user_name} and acknowledging their progress.

## VOICE OUTPUT RULES (STRICT)
These rules exist because your words are spoken aloud by a text-to-speech engine. Breaking them makes the audio sound broken or robotic.
- **No markdown ever.** Never use *, **, #, bullet dashes, or any other formatting symbol. They will be read out literally.
- **No asterisks.** Never write *word* or **word** for emphasis. Speak naturally instead.
- **Numbered points only.** If you must list items, use "First, ... Second, ... Third, ..." or "One, ... Two, ... Three, ..." — never hyphens or asterisks.
- **Plain prose.** Write as you would speak. Short sentences. Natural pauses implied by commas and periods.
- **Recall, don't "search".** When referencing past conversations, say things like "I remember we talked about...", "If I recall correctly...", or "Last time you mentioned..." — never say "let me search" or "I found" as if you are a database query.

## INITIAL TASK
Greet {user_name} and ask how their energy levels are today."""

    # If there are commitments from the previous session, surface them so the
    # bot can naturally follow up ("Last time you said you'd try yoga — did you?")
    # Prefer structured metadata dict (from DB); fall back to regex on summary text.
    commitments = None
    if previous_session_metadata:
        val = previous_session_metadata.get("commitments", "")
        if val and val.lower() not in ("none", "n/a", "-", ""):
            commitments = val
    elif previous_session_summary:
        commitments = _extract_commitments_from_summary(previous_session_summary)
    if commitments:
        prompt += f"""

## FOLLOW-UP FROM LAST SESSION
{user_name} made the following commitment last session: "{commitments}"
Early in this conversation, gently ask {user_name} how it went — but only once, naturally, not as an interrogation."""

    if non_english:
        prompt += f"""

## LANGUAGE
{user_name} is speaking in **{display_name}**. You must:
- Understand and respond to everything {user_name} says in {display_name}.
- **Always reply in English.** The voice system only speaks English, so your responses must be in English even when {user_name} speaks {display_name}.
- Be warm and natural — do not mention this constraint to {user_name}.
- If {user_name} uses a {display_name} word that has no English equivalent, gently use the English nearest to it.
- Session memory and notes are stored in English — this happens automatically."""

    # ── size validation ────────────────────────────────────────────────────────
    prompt_size = len(prompt)
    estimated_tokens = estimate_tokens(prompt)

    if prompt_size > settings.SYSTEM_PROMPT_MAX_SIZE:
        logger.warning(
            f"⚠️  Base system prompt exceeds recommended size: {prompt_size} chars "
            f"({estimated_tokens} tokens) > {settings.SYSTEM_PROMPT_MAX_SIZE} chars"
        )
    if prompt_size > settings.SYSTEM_PROMPT_ERROR_SIZE:
        logger.error(
            f"❌ Base system prompt exceeds error threshold: {prompt_size} chars "
            f"({estimated_tokens} tokens) > {settings.SYSTEM_PROMPT_ERROR_SIZE} chars"
        )

    logger.debug(
        f"📋 Built system prompt: language={display_name}, "
        f"{prompt_size} chars ({estimated_tokens} tokens)"
    )

    return prompt.strip()


def build_system_prompt_with_past_context(
    user_name: str,
    past_context: str = "",
    bot_name: Optional[str] = None,
    language_code: Optional[str] = None,
) -> str:
    """Build complete system prompt with optional past context."""
    base_prompt = build_base_system_prompt(user_name, bot_name, language_code)
    if not past_context:
        return base_prompt

    complete_prompt = base_prompt + "\n\n" + past_context
    complete_size = len(complete_prompt)
    estimated_tokens = estimate_tokens(complete_prompt)

    if complete_size > settings.SYSTEM_PROMPT_MAX_SIZE:
        logger.warning(
            f"⚠️  Complete system prompt exceeds recommended size: "
            f"{complete_size} chars ({estimated_tokens} tokens)"
        )

    logger.debug(
        f"📋 Built complete system prompt: {complete_size} chars ({estimated_tokens} tokens)"
    )

    return complete_prompt.strip()