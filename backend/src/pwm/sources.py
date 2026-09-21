"""Normalized source records.

A SourceRecord is what a connector produces and what the pipeline consumes. It is
immutable, and its text is untrusted third-party content: data, never instructions.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceKind(StrEnum):
    EMAIL = "email"
    CALENDAR_EVENT = "calendar_event"
    USER_CAPTURE = "user_capture"


MAX_BODY = 200_000
MAX_NAME, MAX_ADDRESS, MAX_ID = 200, 320, 200


def _clean(text: str) -> str:
    # PostgreSQL text cannot hold NUL or lone surrogates, and nothing a person wrote needs them.
    return text.replace("\x00", "").encode("utf-8", "ignore").decode("utf-8")


class Party(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = None
    address: str

    @field_validator("name", mode="before")
    @classmethod
    def _bounded_name(cls, value: object) -> object:
        return _clean(value)[:MAX_NAME] if isinstance(value, str) else value

    @field_validator("address", mode="before")
    @classmethod
    def _real_address(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        address = _clean(value).strip()
        # Truncating an address would make it somebody else's. Too long is simply invalid.
        if len(address) > MAX_ADDRESS or "@" not in address:
            raise ValueError("not an email address")
        return address


class SourceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: SourceKind
    observed_at: datetime
    thread_id: str | None = None
    sender: Party | None = None
    recipients: tuple[Party, ...] = ()
    subject: str = ""
    body: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    provider_labels: tuple[str, ...] = ()
    # Calendar-only fields.
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None
    event_status: str | None = None

    @field_validator("id", "thread_id", mode="before")
    @classmethod
    def _bounded_id(cls, value: object) -> object:
        if isinstance(value, str) and not 0 < len(value) <= MAX_ID:
            raise ValueError("identifier is empty or too long")
        return value

    @field_validator("observed_at", "starts_at", "ends_at", mode="after")
    @classmethod
    def _sane_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)  # a naive time among aware ones cannot be sorted
        if not 1970 <= value.year <= 2200:
            raise ValueError("timestamp is outside any plausible range")
        return value

    @field_validator("subject", "body", "location", mode="before")
    @classmethod
    def _sanitize(cls, value: object) -> object:
        # Bounded as well: a megabyte of markup is an attack on the parser, not a letter.
        return _clean(value)[:MAX_BODY] if isinstance(value, str) else value

    @property
    def text(self) -> str:
        """The text that evidence quotes are verified against."""
        return f"{self.subject}\n{self.body}"
