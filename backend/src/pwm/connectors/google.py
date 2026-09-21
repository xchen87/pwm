"""Normalizing Gmail and Google Calendar API payloads into source records.

Pure functions over the documented JSON shapes (users.messages.get with format=full;
events.list items). Fetching, OAuth, and token storage are not here: they need a Google
OAuth client to build against and verify, which this project does not have yet.
"""

import base64
import binascii
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from email.utils import getaddresses
from html import unescape
from typing import Any

from pwm import clock
from pwm.pipeline.text import strip_hidden_markup
from pwm.sources import Party, SourceKind, SourceRecord


class MalformedPayload(ValueError):
    """A provider payload that cannot be turned into a record. Carries no content."""


KEPT_HEADERS = ("List-Unsubscribe", "Precedence", "Auto-Submitted", "Authentication-Results")


def _required_id(payload: dict[str, Any]) -> str:
    identifier = payload["id"]
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("missing id")
    return identifier


def _parties(value: str) -> tuple[Party, ...]:
    return tuple(
        Party(name=n or None, address=a.lower()) for n, a in getaddresses([value]) if "@" in a
    )


def _decoded(part: dict[str, Any]) -> str:
    data = part.get("body", {}).get("data") or ""
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _html_part(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/html" and not payload.get("filename"):
        return _decoded(payload)
    for part in payload.get("parts") or []:
        if html := _html_part(part):
            return html
    return ""


def _html_to_text(html: str) -> str:
    """For mail with no plain-text part. Hidden elements go first, so text a reader would
    never see does not become the body; then tags, then entities."""
    visible = strip_hidden_markup(html)
    visible = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", visible)
    visible = re.sub(r"(?i)<(br|/p|/div|/tr|/li|/h[1-6])\b[^<>]*>", "\n", visible)
    return unescape(re.sub(r"<[^<>]*>", "", visible)).strip()


def _plain_text(payload: dict[str, Any]) -> str:
    """The text/plain part: the sender's words without markup."""
    if payload.get("mimeType") == "text/plain" and (data := payload.get("body", {}).get("data")):
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
    for part in payload.get("parts") or []:
        if part.get("filename"):
            continue  # an attached .txt file is not the body of the message
        if text := _plain_text(part):
            return text
    return ""


def gmail_message(message: dict[str, Any]) -> SourceRecord:
    try:
        return _gmail_message(message)
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        RecursionError,
        OverflowError,
        OSError,
        binascii.Error,
    ) as problem:
        raise MalformedPayload(type(problem).__name__) from None


def _gmail_message(message: dict[str, Any]) -> SourceRecord:
    payload = message.get("payload") or {}
    headers: dict[str, str] = {}
    for header in payload.get("headers") or []:
        # The first occurrence wins: a second From header is a classic spoofing trick.
        headers.setdefault(str(header["name"]).lower(), str(header.get("value", "")))
    body = _plain_text(payload) or _html_to_text(_html_part(payload))
    senders = _parties(headers.get("from", ""))
    recipients = _parties(", ".join(filter(None, (headers.get("to"), headers.get("cc")))))
    observed = datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, UTC)
    return SourceRecord(
        id=f"gmail:{_required_id(message)}",
        kind=SourceKind.EMAIL,
        observed_at=observed,
        thread_id=f"gmail:{message.get('threadId', message['id'])}",
        sender=senders[0] if senders else None,
        recipients=recipients,
        subject=headers.get("subject", ""),
        body=body,
        headers={k: headers[k.lower()] for k in KEPT_HEADERS if k.lower() in headers},
        provider_labels=tuple(message.get("labelIds", [])),
    )


def _moment(value: dict[str, Any] | None) -> datetime | None:
    if not value:
        return None
    if "dateTime" in value:
        return _aware(value["dateTime"])
    return datetime.fromisoformat(value["date"]).replace(tzinfo=UTC) if "date" in value else None


def calendar_event(event: dict[str, Any], owner: Party) -> SourceRecord:
    try:
        return _calendar_event(event, owner)
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        RecursionError,
        OverflowError,
    ) as problem:
        raise MalformedPayload(type(problem).__name__) from None


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _calendar_event(event: dict[str, Any], owner: Party) -> SourceRecord:
    # A deletion arrives as little more than {id, status: "cancelled"}. Stamped now, it is
    # the newest version of the event, which is what makes the cancellation take effect.
    updated = event.get("updated") or event.get("created") or clock.now().isoformat()
    attendees = tuple(
        Party(name=a.get("displayName"), address=a["email"].lower())
        for a in event.get("attendees", [])
        if a.get("email") and not a.get("self") and a["email"].lower() != owner.address.lower()
    )
    return SourceRecord(
        # An edited event is a new, immutable source: the id carries its version.
        id=f"gcal:{_required_id(event)}@{updated}"[:200],
        kind=SourceKind.CALENDAR_EVENT,
        observed_at=_aware(updated),
        sender=owner,
        recipients=attendees,
        subject=event.get("summary") or "",
        body=event.get("description") or "",
        starts_at=_moment(event.get("start")),
        ends_at=_moment(event.get("end")),
        location=event.get("location"),
        event_status=event.get("status"),
    )


def normalize_all[T](
    payloads: Iterable[T], normalize: Callable[[T], SourceRecord]
) -> tuple[list[SourceRecord], int]:
    """Normalize what can be normalized and count what cannot: one malformed message must
    not stop a sync."""
    records: list[SourceRecord] = []
    skipped = 0
    for payload in payloads:
        try:
            records.append(normalize(payload))
        except MalformedPayload:
            skipped += 1
    return records, skipped
