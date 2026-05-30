"""Authentication and token generation routes."""

import asyncio
import json
import os
import time
import urllib.request
from typing import Optional

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse
from livekit import api
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.exceptions import ValidationError

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


async def _wake_agent_if_configured() -> None:
    """Best-effort wake-up ping for Cloud Run agent when min-instances is zero."""
    wake_url = (settings.AGENT_WAKE_URL or "").strip()
    if not wake_url:
        return

    start = time.monotonic()
    timeout = max(1, int(settings.AGENT_WAKE_TIMEOUT_SECONDS))
    req = urllib.request.Request(wake_url, method="GET")
    try:
        await asyncio.to_thread(urllib.request.urlopen, req, timeout=timeout)
        duration = time.monotonic() - start
        logger.info(f"Agent wake ping succeeded in {duration:.2f}s")
    except Exception as e:
        duration = time.monotonic() - start
        logger.warning(f"Agent wake ping failed after {duration:.2f}s: {e}")


class TokenResponse(BaseModel):
    """Token response model."""

    room_name: str = Field(..., description="LiveKit room name")
    token: str = Field(..., description="JWT access token")
    url: str = Field(..., description="LiveKit WebSocket URL")


@router.get(
    "/connect",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate LiveKit access token",
    description="Generate a LiveKit access token for a user to join a voice session",
)
async def get_token(
    user: str = Query(
        ...,
        description="The user's display name",
        min_length=1,
        max_length=100,
    ),
    language: str = Query(
        default="en",
        description="BCP-47 language code for STT (e.g. 'hi', 'ta', 'en')",
        min_length=2,
        max_length=10,
    ),
) -> TokenResponse:
    """Generate LiveKit access token for user.

    Args:
        user:     User's display name.
        language: Session language code — passed to the bot via participant
                  metadata so it can configure Deepgram STT correctly.

    Returns:
        TokenResponse with room name, token, and URL.
    """
    try:
        if not user or not user.strip():
            raise ValidationError("User name cannot be empty")

        user = user.strip()
        language = language.strip().lower() or "en"

        logger.info(f"Generating token for user: {user}, language: {language}")

        # When agent runs with min-instances=0, this ping wakes Cloud Run
        # before frontend attempts to join the room.
        await _wake_agent_if_configured()

        room_name = f"room_{int(os.urandom(4).hex(), 16)}"

        token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(user)
            .with_grants(api.VideoGrants(room_join=True, room=room_name))
        )

        # Pass user_name and preferred_language to the bot via participant metadata.
        # bot/main.py reads both fields when the participant joins the room.
        token.with_metadata(
            json.dumps({
                "user_name": user,
                "preferred_language": language,
            })
        )

        livekit_url = settings.LIVEKIT_PUBLIC_URL or settings.LIVEKIT_URL

        response = TokenResponse(
            room_name=room_name,
            token=token.to_jwt(),
            url=livekit_url,
        )

        logger.info(
            f"Token generated: user={user}, language={language}, room={room_name}"
        )
        return response

    except Exception as e:
        logger.error(f"Error generating token: {e}", exc_info=True)
        raise