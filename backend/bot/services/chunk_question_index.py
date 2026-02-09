"""Chunk-question indexing for semantic recall."""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.embedding_service import generate_embedding
from bot.services.topic_extractor import extract_topics_from_user_messages_hybrid

logger = get_logger(__name__)


def _chunk_transcript(
    transcript: List[Dict[str, Any]],
    max_messages: int,
    max_chars: int
) -> List[Dict[str, Any]]:
    """Split transcript into chunks of messages with size limits."""
    chunks: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_chars = 0

    for msg in transcript:
        if msg.get("role") not in ["user", "assistant"]:
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        preview = f"{msg.get('role')}: {content}"
        if current and (len(current) >= max_messages or current_chars + len(preview) > max_chars):
            chunks.append({"messages": current})
            current = []
            current_chars = 0
        current.append({"role": msg.get("role"), "content": content})
        current_chars += len(preview)

    if current:
        chunks.append({"messages": current})

    return chunks


def _format_chunk_text(messages: List[Dict[str, Any]]) -> str:
    """Format chunk messages into a single text block."""
    lines = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_json_array(text: str) -> List[str]:
    """Parse a JSON array from an LLM response."""
    if not text:
        return []
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if str(t).strip()]
    except json.JSONDecodeError:
        pass

    # Fallback: extract first JSON-like array
    import re
    matches = re.findall(r"\[.*?\]", text, re.DOTALL)
    for match in matches:
        try:
            parsed = json.loads(match)
            if isinstance(parsed, list):
                return [str(t).strip() for t in parsed if str(t).strip()]
        except json.JSONDecodeError:
            continue
    return []


async def _generate_chunk_questions(chunk_text: str, user_name: str) -> List[str]:
    """Generate stand-alone questions for a chunk."""
    if not chunk_text or not chunk_text.strip():
        return []
    if not getattr(settings, "GROQ_API_KEY", None):
        return []

    question_count = max(1, int(settings.CHUNK_QUESTION_COUNT))
    prompt = f"""Review the transcript chunk and generate {question_count} searchable questions a user might ask a voice assistant to recall their history.

Transcript chunk:
{chunk_text}

Return ONLY a JSON array of questions. Example:
["Did the user mention Zumba?", "What time is the Zumba class?"]"""

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
                                "You generate concise, stand-alone searchable questions "
                                "from transcript chunks. Return ONLY a JSON array."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 150,
                },
            )
            response.raise_for_status()
            result = response.json()
            raw = result["choices"][0]["message"]["content"].strip()
            questions = _parse_json_array(raw)
            return questions[:question_count]
    except Exception as e:
        logger.debug(f"Chunk question generation failed: {e}")
        return []


async def build_chunk_question_rows(
    transcript: List[Dict[str, Any]],
    user_name: str,
    room_name: str
) -> List[Dict[str, Any]]:
    """Create chunk question rows (without DB insert)."""
    if not settings.ENABLE_CHUNK_QUESTION_INDEX:
        return []

    chunks = _chunk_transcript(
        transcript,
        max_messages=settings.CHUNK_MAX_MESSAGES,
        max_chars=settings.CHUNK_MAX_TEXT_CHARS,
    )

    rows: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks, 1):
        chunk_text = _format_chunk_text(chunk["messages"])
        questions = await _generate_chunk_questions(chunk_text, user_name)
        if not questions:
            continue

        user_messages = [m.get("content", "") for m in chunk["messages"] if m.get("role") == "user"]
        topics = await extract_topics_from_user_messages_hybrid(user_messages)
        topics = topics or []

        for question_text in questions:
            embedding = None
            if settings.ENABLE_SEMANTIC_SEARCH and settings.ENABLE_CHUNK_QUESTION_SEMANTIC_MATCHING:
                embedding = await generate_embedding(question_text)
            rows.append({
                "room_name": room_name,
                "user_name": user_name.lower().strip(),
                "chunk_index": idx,
                "question_text": question_text.strip(),
                "chunk_text": chunk_text,
                "topics": topics,
                "question_embedding": embedding,
            })

    return rows

