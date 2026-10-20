from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: Literal["dev", "staging", "prod"] = "dev"
    DB_TARGET: Literal["local", "remote"] = "local"

    # No default — app refuses to start if unset (prevents forged tokens on misconfigured deploys).
    SUPABASE_JWT_SECRET: str

    # Local Supabase defaults (supabase start)
    LOCAL_DB_HOST: str = "localhost"
    LOCAL_DB_PORT: int = 54322
    LOCAL_DB_USER: str = "postgres"
    LOCAL_DB_PASSWORD: str = "postgres"
    LOCAL_DB_NAME: str = "postgres"

    # ES256 JWKS endpoint — app refuses to start if unset.
    # Local:  http://127.0.0.1:54321/auth/v1/.well-known/jwks.json
    # Remote: https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
    SUPABASE_JWKS_URL: str = ""
    # Expected iss claim — app refuses to start if unset.
    # Local:  http://127.0.0.1:54321/auth/v1
    # Remote: https://<project-ref>.supabase.co/auth/v1
    SUPABASE_ISSUER: str = ""

    @model_validator(mode="after")
    def _require_jwt_endpoints(self) -> "Settings":
        if not self.SUPABASE_JWKS_URL:
            raise ValueError("SUPABASE_JWKS_URL must be set")
        if not self.SUPABASE_ISSUER:
            raise ValueError("SUPABASE_ISSUER must be set")
        if not self.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY must be set")
        return self

    # Remote Supabase (required when DB_TARGET=remote)
    SUPABASE_HOST: str = ""
    SUPABASE_PROJECT_REF: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_URL: str = ""
    SECRET_KEY: str = ""

    # Supabase Storage API — URL and key MUST point at the same stack.
    # Defaults are the local stack: the key is the public supabase-demo
    # service key (same constant as scripts/seed_dev_users.py, only valid
    # for 127.0.0.1:54321). Remote deploys override BOTH in .env.
    STORAGE_URL: str = "http://127.0.0.1:54321/storage/v1"
    STORAGE_SERVICE_KEY: str = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0"
        ".EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
    )

    # Anthropic — required at startup; prevents a silent triage_pending hang.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_WORKSPACE_ID: str = ""

    TIMEZONE: str = "America/Toronto"
    TRIAGE_PROMPT_DIR: Path = _REPO_ROOT / "docs" / "client-ai-system"

    # Weather escalation (SoW 3.4) — DRAFT feature, off by default.
    # Set WEATHER_ESCALATION_ENABLED=true in .env to turn it on locally.
    WEATHER_ESCALATION_ENABLED: bool = False

    # Comma-separated browser origins allowed to call the API (Railway frontend URL).
    # Empty = no cross-origin (local Vite proxies same-origin, so leave blank locally).
    CORS_ORIGINS: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
