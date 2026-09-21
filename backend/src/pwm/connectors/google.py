"""Normalizing Gmail and Google Calendar API payloads into source records.

Pure functions over the documented JSON shapes (users.messages.get with format=full;
events.list items). Fetching, OAuth, and token storage are not here: they need a Google
OAuth client to build against and verify, which this project does not have yet.
"""

import base64
from datetime import UTC, datetime
from email.utils import getaddresses
from typing import Any

from pwm.sources import Party, SourceKind, SourceRecord

KEPT_HEADERS = ("List-Unsubscribe", "Precedence", "Auto-Submitted", "Authentication-Results")


def _parties(value: str) -> tuple[Party, ...]:
    return tuple(Party(name=n or None, address=a.lower()) for n, a in getaddresses([value]) if a)


def _plain_text(payload: dict[str, Any]) -> str:
    """The text/plain part, which is what the sender's words are; HTML is not used."""
    if payload.get("mimeType") == "text/plain" and (data := payload.get("body", {}).get("data")):
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
    for part in payload.get("parts", []):
        if text := _plain_text(part):
            return text
    return ""


def gmail_message(message: dict[str, Any]) -> SourceRecord:
    payload = message.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    senders = _parties(headers.get("from", ""))
    recipients = _parties(", ".join(filter(None, (headers.get("to"), headers.get("cc")))))
    observed = datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, UTC)
    return SourceRecord(
        id=f"gmail:{message['id']}",
        kind=SourceKind.EMAIL,
        observed_at=observed,
        thread_id=f"gmail:{message.get('threadId', message['id'])}",
        sender=senders[0] if senders else None,
        recipients=recipients,
        subject=headers.get("subject", ""),
        body=_plain_text(payload),
        headers={k: headers[k.lower()] for k in KEPT_HEADERS if k.lower() in headers},
        provider_labels=tuple(message.get("labelIds", [])),
    )


def _moment(value: dict[str, Any] | None) -> datetime | None:
    if not value:
        return None
    if "dateTime" in value:
        parsed = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.fromisoformat(value["date"]).replace(tzinfo=UTC) if "date" in value else None


def calendar_event(event: dict[str, Any], owner: Party) -> SourceRecord:
    updated = event.get("updated") or event.get("created") or "1970-01-01T00:00:00Z"
    attendees = tuple(
        Party(name=a.get("displayName"), address=a["email"].lower())
        for a in event.get("attendees", [])
        if a.get("email") and not a.get("self") and a["email"].lower() != owner.address.lower()
    )
    return SourceRecord(
        id=f"gcal:{event['id']}",
        kind=SourceKind.CALENDAR_EVENT,
        observed_at=datetime.fromisoformat(updated.replace("Z", "+00:00")),
        sender=owner,
        recipients=attendees,
        subject=event.get("summary", ""),
        body=event.get("description", ""),
        starts_at=_moment(event.get("start")),
        ends_at=_moment(event.get("end")),
        location=event.get("location"),
        event_status=event.get("status"),
    )
