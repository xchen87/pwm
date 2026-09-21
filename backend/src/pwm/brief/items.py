"""What is worth telling the user, decided in code.

Selection, ranking, and de-duplication happen here, over stored assertions. A writer
(template or model) only words the items it is given; it cannot add, drop, or alter
facts, and every item keeps the id of the assertion it came from.
"""

from datetime import date, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session, aliased

from pwm.db.models import Assertion, AssertionRelation, User

DEADLINE_HORIZON_DAYS = 10
CONSUMER_HORIZON_DAYS = 45
CONSUMER_PREDICATES = {
    "monthly_price",
    "annual_premium",
    "monthly_rent",
    "return_window_ends",
    "expires",
}
MAX_ITEMS = 12
# A brief is not a to-do list: a few guesses to review, never a wall of them.
MAX_PER_KIND = {"possible_commitment": 4}


class ItemKind(StrEnum):
    DUE_SOON = "due_soon"  # a confirmed commitment or deadline coming up or overdue
    CHANGED = "changed"  # a fact that was updated by a later source
    CONFLICT = "conflict"  # two independent sources disagree
    POSSIBLE_COMMITMENT = "possible_commitment"  # awaiting the user's review
    CONSUMER = "consumer"  # price change, renewal, return window
    REMEMBERED = "remembered"  # something the user asked to remember, now relevant


# Lower sorts first. Mirrors the order in prompts/world_brief.md.
PRIORITY = {
    ItemKind.DUE_SOON: 0,
    ItemKind.CONFLICT: 1,
    ItemKind.CHANGED: 2,
    ItemKind.POSSIBLE_COMMITMENT: 3,
    ItemKind.CONSUMER: 4,
    ItemKind.REMEMBERED: 5,
}


class BriefItem(BaseModel):
    kind: ItemKind
    assertion_id: UUID
    # The assertion this one replaced or disagrees with, for CHANGED and CONFLICT.
    other_assertion_id: UUID | None = None
    subject: str
    predicate: str
    value: str
    previous_value: str | None = None
    due: date | None = None
    overdue: bool = False
    is_fact: bool
    confidence: str
    evidence_quote: str
    other_evidence_quote: str | None = None
    source_label: str
    observed_at: datetime


def _is_fact(assertion: Assertion) -> bool:
    # Confirmed by the user, or the user's own words kept verbatim. An *interpretation* of
    # a note (a due date read out of it, say) is still a guess until they confirm it.
    return assertion.review == "confirmed" or assertion.kind == "memory"


def _label(assertion: Assertion) -> str:
    sender = (assertion.source.record.get("sender") or {}) if assertion.source else {}
    who = sender.get("name") or sender.get("address") or "You"
    subject = assertion.source.record.get("subject") or "note"
    return f"{who} · {subject}"


def _shown_value(a: Assertion) -> str:
    # For a commitment the thing that changes or conflicts is its date, not its wording.
    return a.due.isoformat() if a.kind == "commitment" and a.due else a.value


def _item(kind: ItemKind, a: Assertion, today: date, other: Assertion | None = None) -> BriefItem:
    compared = other is not None
    return BriefItem(
        kind=kind, assertion_id=a.id, other_assertion_id=other.id if other else None,
        subject=a.value if a.kind == "commitment" and compared else a.subject,
        predicate=a.predicate, value=_shown_value(a) if compared else a.value,
        previous_value=_shown_value(other) if other else None, due=a.due,
        overdue=a.due is not None and a.due < today and a.status == "open",
        is_fact=_is_fact(a), confidence=a.confidence, evidence_quote=a.evidence_quote,
        other_evidence_quote=other.evidence_quote if other else None,
        source_label=_label(a), observed_at=a.observed_at,
    )  # fmt: skip


def _live(user: User) -> list[ColumnElement[bool]]:
    return [
        Assertion.user_id == user.id,
        Assertion.superseded_by_id.is_(None),
        Assertion.review.in_(("unreviewed", "confirmed")),
    ]


def select_items(session: Session, user: User, since: datetime, now: datetime) -> list[BriefItem]:
    today = now.date()
    items: list[BriefItem] = []

    commitments = session.scalars(
        select(Assertion).where(
            *_live(user), Assertion.kind == "commitment", Assertion.status == "open"
        )  # fmt: skip
    ).all()
    horizon = today + timedelta(days=DEADLINE_HORIZON_DAYS)
    for c in commitments:
        if _is_fact(c) and c.due is not None and c.due <= horizon:
            items.append(_item(ItemKind.DUE_SOON, c, today))
        elif not _is_fact(c) and (c.observed_at >= since or (c.due and c.due <= horizon)):
            items.append(_item(ItemKind.POSSIBLE_COMMITMENT, c, today))

    newer, older = aliased(Assertion), aliased(Assertion)
    relations = session.execute(
        select(AssertionRelation.type, newer, older)
        .join(newer, AssertionRelation.from_id == newer.id)
        .join(older, AssertionRelation.to_id == older.id)
        .where(AssertionRelation.user_id == user.id, newer.observed_at >= since)
    ).all()
    for relation_type, new, old in relations:
        if new.extraction_method == "user_correction" or new.review == "rejected":
            continue  # the user's own edits are not news to them
        if relation_type == "supersedes" and new.superseded_by_id is None:
            items.append(_item(ItemKind.CHANGED, new, today, old))
        elif relation_type == "contradicts" and old.review != "rejected":
            items.append(_item(ItemKind.CONFLICT, new, today, old))

    consumer_horizon = today + timedelta(days=CONSUMER_HORIZON_DAYS)
    things = session.scalars(
        select(Assertion).where(*_live(user), Assertion.predicate.in_(CONSUMER_PREDICATES))
    ).all()
    for t in things:
        takes_effect = t.valid_from or t.valid_to
        if takes_effect is None or not (today <= takes_effect <= consumer_horizon):
            continue
        kind = ItemKind.REMEMBERED if t.origin == "user_stated" else ItemKind.CONSUMER
        items.append(_item(kind, t, today))

    return _rank(_dedupe(items))


def _dedupe(items: list[BriefItem]) -> list[BriefItem]:
    """One item per assertion: keep the most important reason for mentioning it."""
    best: dict[UUID, BriefItem] = {}
    for item in sorted(items, key=lambda i: PRIORITY[i.kind]):
        mentioned = {item.assertion_id, item.other_assertion_id} - {None}
        if not any(m in best for m in mentioned):
            best[item.assertion_id] = item
    return list(best.values())


def _rank(items: list[BriefItem]) -> list[BriefItem]:
    confidence = {"high": 0, "medium": 1, "low": 2}
    ranked = sorted(
        items,
        key=lambda i: (PRIORITY[i.kind], confidence.get(i.confidence, 3), i.due or date.max),
    )
    # Low-confidence guesses are not worth interrupting someone for.
    kept: list[BriefItem] = []
    for item in ranked:
        if not item.is_fact and item.confidence == "low":
            continue
        limit = MAX_PER_KIND.get(item.kind.value)
        if limit is not None and sum(k.kind is item.kind for k in kept) >= limit:
            continue
        kept.append(item)
    return kept[:MAX_ITEMS]
