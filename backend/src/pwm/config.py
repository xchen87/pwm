from datetime import datetime
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every variable is documented in docs/env.md."""

    model_config = SettingsConfigDict(env_prefix="PWM_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pwm:pwm@localhost:5433/pwm"
    # Fails closed. Only "local" serves the development user without a session, offers the
    # demo mailbox, and accepts Expo Go redirects; it must be asked for explicitly
    # (scripts/demo.sh, scripts/verify.sh and the test suites do).
    environment: str = "production"
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

    # Without a session, serve the local development user. Only ever honoured when
    # environment is "local"; everywhere else a session is required.
    dev_login: bool = True
    session_days: int = 30

    # Google sign-in and read-only Gmail/Calendar. Unset means "not available".
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Public URL of this API, used to build the OAuth callback address.
    public_url: str = "http://localhost:8000"
    # Where the app may be sent after sign-in. Anything else is refused (no open redirects).
    # Exact matches only (scheme, host, path). Expo Go's exp://<host>/--/auth is accepted in
    # a local environment and nowhere else.
    app_redirects: list[str] = ["pwm://auth", "http://localhost:8081/auth"]
    # Overridable so tests and local development can point at a stand-in for Google.
    google_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_revoke_url: str = "https://oauth2.googleapis.com/revoke"
    google_userinfo_url: str = "https://openidconnect.googleapis.com/v1/userinfo"
    google_api_url: str = "https://www.googleapis.com"
    backfill_days: int = 90
    # How often `pwm.cli tick` asks each connection for what is new.
    sync_minutes: int = 15

    # Base64 of 32 random bytes. Encrypts refresh tokens and message bodies at rest.
    # How to generate one: docs/env.md.
    data_key: str | None = None
    # Previous keys, still accepted for reading, so the key can be rotated (see `cli reseal`).
    data_keys_old: list[str] = []

    @property
    def is_local(self) -> bool:
        """Local development, and believably so: a server that says "local" while announcing a
        public address is misconfigured, and is treated as production."""
        host = urlsplit(self.public_url).hostname or ""
        return self.environment == "local" and host in ("localhost", "127.0.0.1", "::1")

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.data_key)


def get_settings() -> Settings:
    return Settings()
