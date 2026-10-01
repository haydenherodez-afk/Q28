from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HERICR_", extra="ignore")

    app_name: str = "HericR"
    database_url: str = "sqlite:///./data/hericr.db"
    secret_key: str = "change-me-in-production-please-32+chars"
    token_minutes: int = 60 * 12
    timezone: str = "Europe/Ljubljana"
    cors_origins: str = "http://localhost:3000"

    # Datoteke: "local" (./data/files) ali "s3" (MinIO / AWS / Hetzner ...)
    storage: str = "local"
    storage_dir: str = "./data/files"
    s3_endpoint: str | None = None
    s3_bucket: str = "hericr"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "eu-central-1"

    # AI (Claude). Brez ključa aplikacija deluje, AI funkcije so izklopljene.
    anthropic_api_key: str | None = None
    ai_model: str = "claude-opus-5-5"

    scheduler_enabled: bool = True
    daily_check_hour: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
