"""The synthetic mailbox as a connector: lets the whole product run with no credentials."""

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from pwm.sources import SourceRecord

FIXTURE = Path(__file__).resolve().parents[4] / "fixtures" / "synthetic" / "sources.json"


class DemoMailbox:
    name = "demo"
    label = "Demo mailbox (synthetic)"

    def fetch(self, since: datetime | None) -> Iterator[SourceRecord]:
        records = [SourceRecord.model_validate(r) for r in json.loads(FIXTURE.read_text("utf-8"))]
        for record in sorted(records, key=lambda r: r.observed_at, reverse=True):
            # >= on purpose: a record stamped exactly at the cursor may be new, and
            # ingestion ignores what it already has.
            if since is None or record.observed_at >= since:
                yield record
