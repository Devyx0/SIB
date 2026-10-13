from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SUPABASE_HOST: str = ""
    SUPABASE_PROJECT_REF: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_URL: str = ""
    SERVICE_ROLE: str = ""
    SECRET_KEY: str = ""

    TRIAGE_PROMPT_DIR: Path = _REPO_ROOT / "docs" / "client-ai-system"


settings = Settings()
