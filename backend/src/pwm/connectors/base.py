"""What every source of data implements.

A connector only fetches and normalizes. It never creates facts: records go through
ingestion and the funnel like everything else.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Protocol

from pwm.sources import SourceRecord


class Connector(Protocol):
    name: str
    label: str

    def fetch(self, since: datetime | None) -> Iterator[SourceRecord]:
        """Records observed after `since`, newest first, so the first useful insight
        does not wait for the whole history."""
        ...
