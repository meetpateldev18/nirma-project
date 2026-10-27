"""
Application Configuration Module — Pydantic Settings & Environment Management.

This module loads, validates, and manages all runtime configuration parameters
for the Nirma Calling Assistant. It enforces externalization of all
carrier secrets, database credentials, AI model endpoints, and institutional domain
bindings via environment variables, strictly adhering to the Twelve-Factor App methodology.

Upstream dependencies:
    - python-dotenv / environment variables (.env)
Downstream dependencies:
    - backend.database.session
    - backend.telephony.plivo_adapter
    - backend.ai_pipeline.*
    - backend.scheduler.*
"""

from typing import Dict, List, Optional
import os
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized application configuration schema loaded from environment variables.

    Attributes:
        app_name: Human-readable service name.
        app_env: Deployment environment ('development', 'staging', 'production').
        debug: Flag enabling verbose diagnostic logging and OpenAPI documentation.
        log_level: Logging severity threshold ('DEBUG', 'INFO', 'WARNING', 'ERROR').
        base_url: Fully qualified institutional domain URL (e.g., 'https://calls.nirmauni.ac.in').
        port: Listening port for the ASGI server.
        allowed_origins: Comma-separated or list of allowed CORS origins.
        database_url: Asynchronous PostgreSQL DSN using asyncpg driver.
        sync_database_url: Synchronous PostgreSQL DSN using psycopg driver for Celery.
        redis_url: Redis DSN for cache, session state, and Celery broker.
        celery_broker_url: Redis broker DSN for Celery tasks.
        celery_result_backend: Redis backend DSN for task execution results.
        plivo_auth_id: Plivo account authentication ID.
        plivo_auth_token: Plivo cryptographic authentication token.
        plivo_caller_id: Registered Indian DID phone number in E.164 format (+91...).
        ollama_base_url: Base endpoint URL for local Ollama LLM inference.
        ollama_model: Tagged model identifier for local LLM inference.
        indic_conformer_model_path: Filesystem path to IndicConformer ASR model checkpoint.
        indic_f5_model_path: Filesystem path to IndicF5 TTS model checkpoint.
        sarvam_api_key: Secret API key for Sarvam AI cloud STT fallback.
        groq_api_key: Secret API key for Groq Cloud LLM fallback.
        jwt_secret_key: Cryptographic symmetric key for JWT signing.
        jwt_algorithm: Hashing algorithm for JWT tokens (default: 'HS256').
        access_token_expire_minutes: Expiration lifetime for JWT access tokens.
        refresh_token_expire_days: Expiration lifetime for JWT refresh tokens.
        audio_cache_dir: Filesystem directory used for caching synthesized TTS audio files.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --------------------------------------------------------------------------
    # Application & Core Runtime
    # --------------------------------------------------------------------------
    app_name: str = Field(default="Nirma Calling Assistant", description="Application service name")
    app_env: str = Field(default="development", description="Runtime environment")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Standard logging level")

    # --------------------------------------------------------------------------
    # Institutional Domain & Networking
    # --------------------------------------------------------------------------
    base_url: str = Field(
        default="https://calls.nirmauni.ac.in",
        description="Institutional domain for reverse proxy and webhook callbacks",
    )
    port: int = Field(default=8000, description="ASGI listening port")
    allowed_origins: str = Field(
        default="http://localhost:3000,https://calls.nirmauni.ac.in",
        description="Comma-separated CORS allowed origins",
    )

    # --------------------------------------------------------------------------
    # Database Configuration (PostgreSQL 15)
    # --------------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@postgres:5432/ai_calls",
        description="Asynchronous PostgreSQL connection string (asyncpg)",
    )
    sync_database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@postgres:5432/ai_calls",
        description="Synchronous PostgreSQL connection string for Celery workers (psycopg)",
    )

    # --------------------------------------------------------------------------
    # Cache & Task Broker (Redis 7)
    # --------------------------------------------------------------------------
    redis_url: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL for caching and state management",
    )
    celery_broker_url: str = Field(
        default="redis://redis:6379/0",
        description="Celery message broker URL",
    )
    celery_result_backend: str = Field(
        default="redis://redis:6379/1",
        description="Celery result backend URL",
    )
    upstash_redis_rest_url: Optional[str] = Field(
        default=None,
        description="Upstash Redis REST API endpoint URL",
    )
    upstash_redis_rest_token: Optional[str] = Field(
        default=None,
        description="Upstash Redis REST API token",
    )

    # --------------------------------------------------------------------------
    # Telephony Providers (Plivo & Twilio)
    # --------------------------------------------------------------------------
    telephony_provider: str = Field(
        default="plivo",
        description="Active PSTN telephony carrier provider: 'plivo' or 'twilio'",
    )
    plivo_auth_id: str = Field(default="", description="Plivo Authentication ID")
    plivo_auth_token: str = Field(default="", description="Plivo Authentication Token")
    plivo_caller_id: str = Field(
        default="+918866241204",
        description="Registered E.164 Caller ID matching Plivo credentials",
    )
    twilio_account_sid: str = Field(
        default="",
        description="Twilio Account SID (e.g. ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx)",
    )
    twilio_auth_token: str = Field(
        default="",
        description="Twilio Cryptographic Authentication Token",
    )
    twilio_caller_id: str = Field(
        default="+918866241204",
        description="Registered E.164 Caller ID matching Twilio credentials",
    )

    # --------------------------------------------------------------------------
    # AI Pipeline — Local Infrastructure
    # --------------------------------------------------------------------------
    ollama_base_url: str = Field(
        default="http://ollama:11434",
        description="Base URL for local Ollama server container",
    )
    ollama_model: str = Field(
        default="qwen3:14b",
        description="Model checkpoint name on local Ollama service",
    )
    indic_conformer_model_path: str = Field(
        default="/models/indicconformer.nemo",
        description="Local path to IndicConformer ASR model file",
    )
    indic_f5_model_path: str = Field(
        default="/models/indicf5.pt",
        description="Local path to IndicF5 TTS model checkpoint",
    )

    # --------------------------------------------------------------------------
    # AI Pipeline — Cloud Fallbacks
    # --------------------------------------------------------------------------
    sarvam_api_key: str = Field(default="", description="API key for Sarvam AI cloud STT fallback")
    groq_api_key: str = Field(default="", description="API key for Groq cloud LLM fallback")
    gemini_api_key: str = Field(default="", description="API key for Google Gemini LLM")
    gemini_tts_api_key: str = Field(
        default="",
        description="Dedicated Google Gemini API key for TTS audio synthesis (falls back to gemini_api_key)",
    )
    gemini_model: str = Field(
        default="gemini-3.8-flash",
        description="Primary Google Gemini model identifier (e.g. 'gemini-3.8-flash')",
    )
    gemini_fallback_model: str = Field(
        default="gemini-3.5-flash-lite",
        description="Fast fallback Gemini model for sub-second failover (e.g. 'gemini-3.5-flash-lite')",
    )
    gemini_tts_model: str = Field(
        default="gemini-3.8-flash-lite-tts",
        description="Gemini voice audio synthesis model (e.g. 'gemini-3.8-flash-lite-tts')",
    )

    # --------------------------------------------------------------------------
    # Security & JWT Tokens
    # --------------------------------------------------------------------------
    jwt_secret_key: str = Field(
        default="super-secret-key-change-in-production-environment-64-hex",
        description="Cryptographic symmetric key for JWT signing",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT token signing algorithm")
    access_token_expire_minutes: int = Field(default=1440, description="Access token TTL in minutes")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token TTL in days")

    # --------------------------------------------------------------------------
    # Static Assets & Audio Cache
    # --------------------------------------------------------------------------
    audio_cache_dir: str = Field(
        default="/app/audio_cache" if os.path.exists("/app") else "/tmp/audio_cache",
        description="Directory for caching synthesized TTS audio files",
    )

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        """Ensures base_url does not end with a trailing slash for uniform URL building."""
        return v.rstrip("/")

    @property
    def cors_origins(self) -> List[str]:
        """
        Parses comma-separated allowed origins into a sanitized list of strings.
        """
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_twilio_active(self) -> bool:
        """
        Returns True if Twilio is configured as the active PSTN telephony carrier.
        """
        return self.telephony_provider.strip().lower() == "twilio"

    @property
    def active_caller_id(self) -> str:
        """
        Returns the registered caller ID matching the active telephony carrier.

        Returns:
            str: E.164 phone number configured for current provider.
        """
        if self.is_twilio_active:
            return self.twilio_caller_id
        return self.plivo_caller_id

    def get_carrier_webhook_urls(self, task_id: int) -> Dict[str, str]:
        """
        Dynamically constructs answer and hangup webhook URLs matching the active carrier.

        Args:
            task_id: Internal primary key identifier of the CallTask.

        Returns:
            Dict[str, str]: Map containing 'answer_url' and 'hangup_url'.
        """
        carrier = "twilio" if self.is_twilio_active else "plivo"
        return {
            "answer_url": self.build_webhook_url(f"/webhook/{carrier}/answer?task_id={task_id}"),
            "hangup_url": self.build_webhook_url(f"/webhook/{carrier}/hangup?task_id={task_id}"),
        }

    def build_webhook_url(self, endpoint_path: str) -> str:
        """
        Dynamically constructs an absolute public webhook callback URL.

        Ensures carrier webhooks are always bound to the university institutional
        domain without hardcoding localhost or static IP addresses.

        Args:
            endpoint_path: Relative URL path (e.g. '/webhook/plivo/answer').

        Returns:
            str: Fully qualified HTTPS URL.
        """
        clean_path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
        return f"{self.base_url}{clean_path}"


# Global singleton instance for settings
settings = Settings()
