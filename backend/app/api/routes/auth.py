"""Authentication and token generation routes."""

import json
import os
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
    user: str = Query(..., description="The user's display name", min_length=1, max_length=100)
) -> TokenResponse:
    """Generate LiveKit access token for user.

    Args:
        user: User's display name.

    Returns:
        TokenResponse with room name, token, and URL.

    Raises:
        ValidationError: If user name is invalid.
    """
    try:
        # Validate user name
        if not user or not user.strip():
            raise ValidationError("User name cannot be empty")

        user = user.strip()
        logger.info(f"Generating token for user: {user}")

        # Generate unique room name
        room_name = f"room_{int(os.urandom(4).hex(), 16)}"

        # Create access token
        token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(user)
            .with_grants(api.VideoGrants(room_join=True, room=room_name))
        )

        # Pass user metadata to bot
        token.with_metadata(
            json.dumps(
                {
                    "user_name": user,
                }
            )
        )

        # Use public URL if set, otherwise fall back to regular URL
        livekit_url = settings.LIVEKIT_PUBLIC_URL or settings.LIVEKIT_URL
        
        response = TokenResponse(
            room_name=room_name,
            token=token.to_jwt(),
            url=livekit_url,
        )

        logger.info(f"Token generated successfully for user: {user}, room: {room_name}")
        return response

    except Exception as e:
        logger.error(f"Error generating token: {e}", exc_info=True)
        raise

