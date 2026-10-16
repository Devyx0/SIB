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
        return self

    # Remote Supabase (required when DB_TARGET=remote)
    SUPABASE_HOST: str = ""
    SUPABASE_PROJECT_REF: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_URL: str = ""
    SERVICE_ROLE: str = ""
    SECRET_KEY: str = ""

    TIMEZONE: str = "America/Toronto"
    TRIAGE_PROMPT_DIR: Path = _REPO_ROOT / "docs" / "client-ai-system"


settings = Settings()
