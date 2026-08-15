from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CareerOS"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://careeros:careeros@localhost:5432/careeros"
    redis_url: str = "redis://localhost:6379/0"
    auto_apply_enabled: bool = False
    minimum_match_score: int = Field(default=75, ge=0, le=100)
    daily_application_target: int = Field(default=20, ge=1, le=100)


@lru_cache
def get_settings() -> Settings:
    return Settings()

