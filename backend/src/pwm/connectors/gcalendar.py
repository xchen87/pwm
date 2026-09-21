"""Google Calendar, read-only: the primary calendar, from the backfill window onwards.

Sources are immutable, so an event that is edited becomes a *new* source (its id carries
the `updated` stamp). Both versions then exist, and reconciliation reports the move as a
change, which is exactly what the user wants to hear about.
"""

import json
from datetime import timedelta
from typing import Any

from pwm import clock
from pwm.connectors.base import FetchResult
from pwm.connectors.google import calendar_event, normalize_all
from pwm.google.account import GoogleAccount
from pwm.google.http import GoogleError
from pwm.sources import Party

EVENTS = "/calendar/v3/calendars/primary/events"


class CalendarConnector:
    name = "google_calendar"
    label = "Google Calendar (read-only)"

    def __init__(self, account: GoogleAccount, owner: Party, backfill_days: int = 90) -> None:
        self._account, self._owner, self._days = account, owner, backfill_days

    def fetch(self, cursor: str | None) -> FetchResult:
        state: dict[str, Any] = json.loads(cursor) if cursor else {}
        if state.get("sync"):
            try:
                return self._collect({"syncToken": state["sync"]})
            except GoogleError as error:
                if error.status not in (400, 410):
                    raise
                # 410 Gone (or a 400 for a token Google no longer accepts): read the window
                # again. Ingestion ignores what it already has.
        since = clock.now() - timedelta(days=self._days)
        # Bounded at both ends: with singleEvents a weekly meeting otherwise expands forever.
        until = clock.now() + timedelta(days=365)
        return self._collect(
            {"timeMin": since.isoformat(), "timeMax": until.isoformat(), "singleEvents": "true"}
        )

    def _collect(self, params: dict[str, Any]) -> FetchResult:
        events: list[dict[str, Any]] = []
        params = {**params, "maxResults": 250}
        while True:
            page = self._account.get(EVENTS, params)
            events.extend(page.get("items") or [])
            if not page.get("nextPageToken"):
                break
            params = {**params, "pageToken": page["nextPageToken"]}
        records, skipped = normalize_all(events, lambda e: calendar_event(e, self._owner))
        return FetchResult(
            records=records, skipped=skipped, cursor=json.dumps({"sync": page.get("nextSyncToken")})
        )
