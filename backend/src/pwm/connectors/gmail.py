"""Gmail, read-only.

First sync: newest first, one page at a time, limited to the backfill window, so the user
sees something within minutes. The history id is captured *before* the backfill starts,
so nothing that arrives during it is missed. After that: incremental, by history id.
If Google has forgotten that history id (404), the backfill starts over; ingestion is
idempotent, so re-reading costs time, not correctness.
"""

import json
from typing import Any

from pwm.connectors.base import FetchResult
from pwm.connectors.google import gmail_message, normalize_all
from pwm.google.account import GoogleAccount
from pwm.google.http import GoogleError

PAGE_SIZE = 50
MAX_RESTARTS = 3
UNWANTED = {"DRAFT", "SPAM", "TRASH"}
ME = "/gmail/v1/users/me"


class GmailConnector:
    name = "gmail"
    label = "Gmail (read-only)"

    def __init__(self, account: GoogleAccount, backfill_days: int = 90) -> None:
        self._account, self._days = account, backfill_days

    def fetch(self, cursor: str | None) -> FetchResult:
        state: dict[str, Any] = json.loads(cursor) if cursor else {}
        if state.get("mode") == "incremental":
            try:
                return self._incremental(str(state["history"]))
            except GoogleError as error:
                if error.status != 404:
                    raise
                state = {}  # history too old: fall through to a fresh backfill
        return self._backfill(state)

    def _backfill(self, state: dict[str, Any]) -> FetchResult:
        history = state.get("history") or self._account.get(f"{ME}/profile")["historyId"]
        params: dict[str, Any] = {
            "q": f"newer_than:{self._days}d -in:draft",
            "maxResults": PAGE_SIZE,
            "includeSpamTrash": "false",
        }
        if state.get("page"):
            params["pageToken"] = state["page"]
        try:
            listing = self._account.get(f"{ME}/messages", params)
        except GoogleError as error:
            restarts = int(state.get("restarts", 0))
            if error.status != 400 or "pageToken" not in params or restarts >= MAX_RESTARTS:
                raise
            state = {**state, "restarts": restarts + 1}
            # The page token went stale mid-backfill. Start the listing again; what was
            # already read is ignored by ingestion.
            params.pop("pageToken")
            listing = self._account.get(f"{ME}/messages", params)
        records, skipped = self._messages([m["id"] for m in listing.get("messages") or []])
        page = listing.get("nextPageToken")
        mode = (
            {"mode": "backfill", "page": page, "restarts": state.get("restarts", 0)}
            if page
            else {"mode": "incremental"}
        )
        return FetchResult(
            records=records,
            skipped=skipped,
            more=bool(page),
            cursor=json.dumps({**mode, "history": str(history)}),
        )

    def _incremental(self, history: str) -> FetchResult:
        ids: list[str] = []
        params: dict[str, Any] = {"startHistoryId": history, "historyTypes": "messageAdded"}
        latest = history
        while True:
            page = self._account.get(f"{ME}/history", params)
            latest = str(page.get("historyId", latest))
            for entry in page.get("history") or []:
                ids.extend(added["message"]["id"] for added in entry.get("messagesAdded") or [])
            if not page.get("nextPageToken"):
                break
            params["pageToken"] = page["nextPageToken"]
        records, skipped = self._messages(list(dict.fromkeys(ids)))
        return FetchResult(
            records=records,
            skipped=skipped,
            cursor=json.dumps({"mode": "incremental", "history": latest}),
        )

    def _messages(self, ids: list[str]) -> tuple[list[Any], int]:
        payloads = []
        missing = 0
        for message_id in ids:
            try:
                payloads.append(
                    self._account.get(f"{ME}/messages/{message_id}", {"format": "full"})
                )
            except GoogleError as error:
                if error.status != 404:
                    raise
                missing += 1  # deleted between listing and fetching
        # An unsent draft is not something the user said, and spam is not something anyone
        # said to them. History reports both, so they are dropped here as well.
        wanted = [p for p in payloads if not UNWANTED & set(p.get("labelIds") or [])]
        records, skipped = normalize_all(wanted, gmail_message)
        return records, skipped + missing
