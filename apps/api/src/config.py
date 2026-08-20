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
    auto_apply_safety_acknowledged: bool = False
    minimum_match_score: int = Field(default=75, ge=0, le=100)
    daily_application_target: int = Field(default=20, ge=1, le=100)
    admin_api_token: str = ""
    default_organization_slug: str = "rodolfo"
    cors_origins: str = "http://localhost:3000"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_auto_apply_enabled(self) -> bool:
        return self.auto_apply_enabled and self.auto_apply_safety_acknowledged


@lru_cache
def get_settings() -> Settings:
    return Settings()
