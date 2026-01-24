"""Configuration management using Pydantic Settings."""

import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Find .env file in project root (two levels up from this file)
_env_file = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    # Application
    APP_NAME: str = "Woka Wellness Voice Assistant"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", description="Environment: development, staging, production")
    DEBUG: bool = Field(default=False, description="Debug mode")

    # API Server
    API_HOST: str = Field(default="0.0.0.0", description="API server host")
    API_PORT: int = Field(default=8000, description="API server port")
    API_PREFIX: str = Field(default="/api/v1", description="API prefix")

    # CORS
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"],
        description="Allowed CORS origins"
    )

    # LiveKit
    LIVEKIT_API_KEY: str = Field(..., description="LiveKit API key")
    LIVEKIT_API_SECRET: str = Field(..., description="LiveKit API secret")
    LIVEKIT_URL: str = Field(default="ws://127.0.0.1:7880", description="LiveKit WebSocket URL")

    # External Services
    GROQ_API_KEY: str = Field(..., description="Groq API key for LLM")
    DEEPGRAM_API_KEY: str = Field(..., description="Deepgram API key for STT")
    CARTESIA_API_KEY: str = Field(..., description="Cartesia API key for TTS")
    CARTESIA_VOICE_ID: str = Field(
        default="faf0731e-dfb9-4cfc-8119-259a79b27e12",
        description="Cartesia voice ID"
    )

    # LLM Configuration
    LLM_MODEL: str = Field(default="llama-3.3-70b-versatile", description="Groq LLM model name")

    # Bot Configuration
    BOT_NAME: str = Field(default="Woka", description="Bot display name")
    VAD_THRESHOLD: float = Field(default=0.5, description="Voice Activity Detection threshold")
    NUM_IDLE_PROCESSES: int = Field(default=3, description="Number of pre-warmed bot processes")

    # Security
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable rate limiting")
    RATE_LIMIT_REQUESTS: int = Field(default=100, description="Rate limit requests per minute")
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Rate limit window in seconds")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v):
        """Validate environment value."""
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}")
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.ENVIRONMENT == "development"


# Global settings instance
settings = Settings()

