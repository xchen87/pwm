from datetime import datetime

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every variable is documented in docs/env.md."""

    model_config = SettingsConfigDict(env_prefix="PWM_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pwm:pwm@localhost:5433/pwm"
    environment: str = "local"
    # Pins the clock for demos of the synthetic mailbox, e.g. 2026-09-12T09:00:00Z.
    fixed_now: datetime | None = None
    # Local development identity; matches the synthetic fixture. Replaced by real auth in Slice 4.
    dev_user_email: str = "alex.rivera@example.com"
    dev_user_name: str = "Alex Rivera"
    # "heuristic" needs no credentials. "anthropic" sends source text to the provider.
    extractor: str = "heuristic"
    triage_model: str = "claude-haiku-4-5"
    extraction_model: str = "claude-opus-5"
    cors_origins: list[str] = ["http://localhost:8081", "http://localhost:19006"]


def get_settings() -> Settings:
    return Settings()
