"""Configuration management using Pydantic Settings."""

import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Find .env file in project root
# This file is at: backend/app/core/config.py
# .env is at: project_root/.env
# So we go up 3 levels from this file
_env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"

# Also check if .env exists in current working directory (for flexibility)
if not _env_file.exists():
    _env_file = Path.cwd() / ".env"
    # If still not found, try going up from cwd
    if not _env_file.exists():
        _env_file = Path.cwd().parent / ".env"


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
        default_factory=lambda: [
            "http://localhost:5173", 
            "http://localhost:3000", 
            "http://localhost:15173",
            "https://app.woka.ai"  # Cloudflare frontend URL
        ],
        description="Allowed CORS origins"
    )

    # LiveKit
    LIVEKIT_API_KEY: str = Field(..., description="LiveKit API key")
    LIVEKIT_API_SECRET: str = Field(..., description="LiveKit API secret")
    LIVEKIT_URL: str = Field(default="ws://127.0.0.1:7880", description="LiveKit WebSocket URL (for agent connection)")
    LIVEKIT_PUBLIC_URL: Optional[str] = Field(
        default=None, 
        description="LiveKit public WebSocket URL (for frontend, defaults to LIVEKIT_URL if not set)"
    )

    # External Services
    GROQ_API_KEY: str = Field(..., description="Groq API key for LLM")
    DEEPGRAM_API_KEY: str = Field(..., description="Deepgram API key for STT and TTS")
    DEEPGRAM_TTS_VOICE: str = Field(
        default="aura-2-helena-en",
        description="Deepgram TTS voice (Aura model)"
    )

    # LLM Configuration
    LLM_MODEL: str = Field(default="llama-3.3-70b-versatile", description="Groq LLM model name")
    SUMMARIZATION_MODEL: str = Field(
        default="llama-3.1-8b-instant", 
        description="Model to use for summarization and memory compression (cheaper/faster)"
    )

    # Bot Configuration
    BOT_NAME: str = Field(default="Woka", description="Bot display name")
    VAD_THRESHOLD: float = Field(default=0.5, description="Voice Activity Detection threshold")
    NUM_IDLE_PROCESSES: int = Field(default=1, description="Number of pre-warmed bot processes")

    # Session History (Supabase)
    SUPABASE_URL: Optional[str] = Field(default=None, description="Supabase project URL")
    SUPABASE_KEY: Optional[str] = Field(default=None, description="Supabase API key")
    SUPABASE_ENABLED: bool = Field(default=False, description="Enable Supabase for session history")

    # Context Management
    MAX_PAST_SESSIONS: int = Field(
        default=2, description="Maximum past sessions to include in context"
    )
    MAX_PAST_CONTEXT_SIZE: int = Field(
        default=8000, description="Maximum past context size in characters"
    )
    MAX_SUMMARY_LENGTH: int = Field(
        default=400, description="Maximum summary length per session in characters"
    )
    SYSTEM_PROMPT_MAX_SIZE: int = Field(
        default=2000, description="Maximum system prompt size in characters (warning threshold)"
    )
    SYSTEM_PROMPT_ERROR_SIZE: int = Field(
        default=3000, description="Maximum system prompt size in characters (error threshold)"
    )
    CONTEXT_WARNING_THRESHOLD: float = Field(
        default=0.8, description="Warning threshold as fraction of model context window (0.8 = 80%)"
    )
    
    # Dynamic Context Management
    ENABLE_DYNAMIC_CONTEXT: bool = Field(
        default=True, description="Enable runtime context querying"
    )
    
    # Memory Management
    ENABLE_CONVERSATION_MEMORY: bool = Field(
        default=True, description="Enable conversation memory management for long sessions"
    )
    ENABLE_INCREMENTAL_SUMMARIES: bool = Field(
        default=True,
        description="Enable incremental running summaries during long sessions (in-memory only)",
    )
    MEMORY_SUMMARIZATION_THRESHOLD: int = Field(
        default=50, description="Message count threshold to trigger summarization"
    )
    MEMORY_KEEP_RECENT: int = Field(
        default=30, description="Number of recent messages to keep in full detail"
    )
    MEMORY_SUMMARY_FREQUENCY: int = Field(
        default=25, description="Summarize every N messages after threshold"
    )
    
    # Performance Monitoring
    ENABLE_PERFORMANCE_MONITORING: bool = Field(
        default=True, description="Enable performance monitoring and metrics collection"
    )
    TRACK_TOKEN_USAGE: bool = Field(
        default=True, description="Track token usage per request"
    )
    TRACK_COSTS: bool = Field(
        default=True, description="Track and log API costs per session"
    )
    PERFORMANCE_LOG_INTERVAL: int = Field(
        default=10, description="Log performance metrics every N requests"
    )
    INITIAL_SESSIONS_COUNT: int = Field(
        default=2, description="Number of sessions to load at startup"
    )
    MAX_DYNAMIC_SESSIONS: int = Field(
        default=2, description="Max sessions to retrieve dynamically (for date/topic queries)"
    )
    MAX_SEMANTIC_SEARCH_RESULTS: int = Field(
        default=5, description="Max sessions to retrieve for semantic search (higher because threshold filters quality)"
    )
    CONTEXT_CACHE_TTL: int = Field(
        default=300, description="Context cache TTL in seconds"
    )
    INTENT_DETECTION_ENABLED: bool = Field(
        default=True, description="Enable intent detection"
    )
    
    # Semantic Search Configuration
    ENABLE_SEMANTIC_SEARCH: bool = Field(
        default=True, description="Enable semantic search with embeddings"
    )
    EMBEDDING_MODEL: str = Field(
        default="local", description="Embedding model name (use 'local' for Sentence Transformers)"
    )
    LOCAL_EMBEDDING_MODEL: str = Field(
        default="all-MiniLM-L6-v2", description="Local SentenceTransformer model name"
    )
    SEMANTIC_SEARCH_THRESHOLD: float = Field(
        default=0.7, description="Minimum similarity threshold for semantic search"
    )
    EMBEDDING_DIMENSION: int = Field(
        default=384, description="Embedding vector dimension (384 for local models, 1536 for OpenAI)"
    )
    OPENAI_API_KEY: Optional[str] = Field(
        default=None, description="OpenAI API key for embeddings (optional, falls back to local model)"
    )
    ENABLE_LLM_TOPIC_FALLBACK: bool = Field(
        default=True, description="Enable LLM-based topic extraction fallback when keyword extraction returns no topics"
    )

    # Security
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable rate limiting")
    RATE_LIMIT_REQUESTS: int = Field(default=100, description="Rate limit requests per minute")
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Rate limit window in seconds")

    # Tracing / Observability
    ENABLE_TRACING: bool = Field(
        default=False, description="Enable OpenTelemetry tracing (Jaeger/OTel collector)"
    )
    JAEGER_ENDPOINT: Optional[str] = Field(
        default=None,
        description="OTLP trace endpoint for Jaeger/OTel collector (e.g. http://localhost:4317)",
    )

    # Langfuse
    ENABLE_LANGFUSE: bool = Field(
        default=False, description="Enable Langfuse observability for dev"
    )
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(
        default=None, description="Langfuse public key"
    )
    LANGFUSE_SECRET_KEY: Optional[str] = Field(
        default=None, description="Langfuse secret key"
    )
    LANGFUSE_HOST: Optional[str] = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse host URL (use http://localhost:3000 for local dev)",
    )
    LANGFUSE_TURN_METRICS_ENABLED: bool = Field(
        default=True, description="Enable turn-by-turn Langfuse metrics"
    )
    LANGFUSE_TURN_METRICS_IN_PROD: bool = Field(
        default=True, description="Allow turn-by-turn Langfuse metrics in production"
    )
    LANGFUSE_TURN_SAMPLE_RATE: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Sampling rate for turn-by-turn metrics"
    )

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

