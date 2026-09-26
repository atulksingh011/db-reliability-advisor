from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_env: str = "development"
    ai_provider: str = "mock"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    database_url: str = "sqlite:///./reliability.db"
    mongodb_uri: str = "mongodb://localhost:27017/reliability_demo"
    prometheus_url: str = "http://localhost:9090"
    loki_url: str = "http://localhost:3100"
    max_analysis_window_minutes: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("ai_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if value not in {"mock", "gemini"}:
            raise ValueError("AI_PROVIDER must be 'mock' or 'gemini'")
        return value

    def validate_provider_configuration(self) -> None:
        if self.ai_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        if self.ai_provider == "gemini" and not self.gemini_model:
            raise ValueError("GEMINI_MODEL is required when AI_PROVIDER=gemini")

@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_provider_configuration()
    return settings
