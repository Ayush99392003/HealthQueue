"""
Healthcare Appointment & Follow-up Manager
Core configuration via pydantic-settings.

All environment variables are loaded from .env at startup.
Missing required variables raise ValidationError immediately — never at runtime.
"""

from functools import lru_cache

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings validated at startup via pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "Healthcare Appointment & Follow-up Manager"
    app_version: str = "0.1.0"
    environment: str = "development"  # development | staging | production
    debug: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:postgres@localhost:5432/healthqueue"

    # ── Security ─────────────────────────────────────────────────────────────
    jwt_secret_key: str = "healthqueue-super-secret-jwt-key-minimum-32-bytes!"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    # Secret key required to self-register as admin — keep this private
    admin_registration_secret: str = ""

    # ── LLM Providers ────────────────────────────────────────────────────────
    default_llm_provider: str = "groq"  # groq | openai | anthropic | gemini | azure
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""

    # ── LLM Timeouts & Retries ───────────────────────────────────────────────
    llm_timeout_seconds: int = 5
    llm_max_retries: int = 2

    # ── Notifications — Twilio WhatsApp ──────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""  # e.g. whatsapp:+14155238886

    # ── Notifications — Email ────────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Healthcare Manager"

    # ── Google Calendar ──────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    google_oauth_encryption_key: str = ""  # Fernet key for encrypting stored tokens

    # ── Queue Engine ─────────────────────────────────────────────────────────
    delay_detection_threshold_minutes: int = 20
    anchor_slot_grace_window_minutes: int = 10
    priority_serve_ratio: int = 4  # 1-in-N priority slots served

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @field_validator("default_llm_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"groq", "openai", "anthropic", "gemini", "azure"}
        if v not in allowed:
            raise ValueError(f"default_llm_provider must be one of {allowed}")
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
