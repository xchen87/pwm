from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every variable is documented in docs/env.md."""

    model_config = SettingsConfigDict(env_prefix="PWM_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pwm:pwm@localhost:5433/pwm"
    environment: str = "local"
    cors_origins: list[str] = ["http://localhost:8081", "http://localhost:19006"]


def get_settings() -> Settings:
    return Settings()
