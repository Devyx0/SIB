from __future__ import annotations

from pathlib import Path
from typing import Literal

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

    # Local Supabase defaults (supabase start)
    LOCAL_DB_HOST: str = "localhost"
    LOCAL_DB_PORT: int = 54322
    LOCAL_DB_USER: str = "postgres"
    LOCAL_DB_PASSWORD: str = "postgres"
    LOCAL_DB_NAME: str = "postgres"

    # Remote Supabase (required when DB_TARGET=remote)
    SUPABASE_HOST: str = ""
    SUPABASE_PROJECT_REF: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_URL: str = ""
    SERVICE_ROLE: str = ""
    SECRET_KEY: str = ""

    TRIAGE_PROMPT_DIR: Path = _REPO_ROOT / "docs" / "client-ai-system"


settings = Settings()
