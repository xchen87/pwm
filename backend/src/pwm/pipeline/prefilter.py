"""Stage 1: deterministic routing. Most mail never reaches a model."""

import re
from enum import StrEnum

from pwm.sources import Party, SourceKind, SourceRecord

_SKIPPED_CATEGORIES = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}
_BULK_HEADERS = ("list-unsubscribe", "auto-submitted")
_NO_REPLY = re.compile(r"^(no-?reply|do-?not-?reply|notifications?|mailer-daemon)@", re.IGNORECASE)
# Automated mail is kept only when it looks transactional: it changes something the user
# owns or owes. Dropping all bulk mail would lose price rises, renewals, and return windows.
_TRANSACTIONAL = re.compile(
    r"\b(price|premium|renews?|renewal|return (this|the|your)|refund|deadline|"
    r"(is|are) due|past due|expires?|rescheduled|appointment|cancell?ed|payment (failed|due))\b",
    re.IGNORECASE,
)


class Route(StrEnum):
    SKIP = "skip"
    TRIAGE = "triage"
    # Calendar entries are already structured: code reads them directly.
    STRUCTURED = "structured"
    # The user's own words go straight to extraction: never triaged away.
    EXTRACT = "extract"


def is_from_user(source: SourceRecord, user: Party) -> bool:
    return source.sender is not None and source.sender.address.lower() == user.address.lower()


def is_bulk(source: SourceRecord) -> bool:
    headers = {name.lower(): value.lower() for name, value in source.headers.items()}
    if any(name in headers for name in _BULK_HEADERS) or headers.get("precedence") in {
        "bulk",
        "list",
        "junk",
    }:
        return True
    return source.sender is not None and bool(_NO_REPLY.match(source.sender.address))


def route(source: SourceRecord, user: Party) -> Route:
    if source.kind is SourceKind.CALENDAR_EVENT:
        return Route.STRUCTURED
    if source.kind is SourceKind.USER_CAPTURE:
        return Route.EXTRACT
    if is_from_user(source, user):
        return Route.TRIAGE
    if _SKIPPED_CATEGORIES & set(source.provider_labels):
        return Route.SKIP
    if is_bulk(source):
        text = f"{source.subject}\n{source.body}"
        return Route.TRIAGE if _TRANSACTIONAL.search(text) else Route.SKIP
    return Route.TRIAGE
