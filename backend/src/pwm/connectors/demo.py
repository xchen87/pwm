"""The synthetic mailbox as a connector: lets the whole product run with no credentials."""

import json
from datetime import datetime
from pathlib import Path

from pwm.connectors.base import FetchResult
from pwm.sources import SourceRecord

FIXTURE = Path(__file__).resolve().parents[4] / "fixtures" / "synthetic" / "sources.json"


def fixture_records() -> list[SourceRecord]:
    return [SourceRecord.model_validate(r) for r in json.loads(FIXTURE.read_text("utf-8"))]


class DemoMailbox:
    name = "demo"
    label = "Demo mailbox (synthetic)"

    def fetch(self, cursor: str | None) -> FetchResult:
        since = datetime.fromisoformat(cursor) if cursor else None
        # >= on purpose: a record stamped exactly at the cursor may be new, and ingestion
        # ignores what it already has.
        records = sorted(
            (r for r in fixture_records() if since is None or r.observed_at >= since),
            key=lambda r: r.observed_at,
            reverse=True,
        )
        newest = max((r.observed_at for r in records), default=since)
        return FetchResult(records=records, cursor=newest.isoformat() if newest else None)
