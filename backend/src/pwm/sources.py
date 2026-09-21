"""Normalized source records.

A SourceRecord is what a connector produces and what the pipeline consumes. It is
immutable, and its text is untrusted third-party content: data, never instructions.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceKind(StrEnum):
    EMAIL = "email"
    CALENDAR_EVENT = "calendar_event"
    USER_CAPTURE = "user_capture"


class Party(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = None
    address: str


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

    @property
    def text(self) -> str:
        """The text that evidence quotes are verified against."""
        return f"{self.subject}\n{self.body}"
