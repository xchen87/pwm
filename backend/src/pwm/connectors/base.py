"""What every source of data implements.

A connector only fetches and normalizes. It never creates facts: records go through
ingestion and the funnel like everything else.
"""

from typing import Protocol

from pydantic import BaseModel

from pwm.sources import SourceRecord


class FetchResult(BaseModel):
    records: list[SourceRecord]
    # Opaque to everyone but the connector that wrote it. Stored and handed back next time.
    cursor: str | None
    # True when this was one page of a longer catch-up: call again soon with the new cursor.
    more: bool = False
    # Payloads that could not be normalized. Counted, never stored.
    skipped: int = 0


class Connector(Protocol):
    name: str
    label: str

    def fetch(self, cursor: str | None) -> FetchResult:
        """The next batch after `cursor`, newest first on a first sync so that the first
        useful insight does not wait for the whole history."""
        ...
