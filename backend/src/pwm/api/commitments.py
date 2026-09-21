from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased

from pwm import clock, review
from pwm.api.deps import CurrentUser, DbSession
from pwm.api.schemas import (
    AssertionDetail,
    CommitmentItem,
    Correction,
    RelatedAssertion,
    SourceSummary,
    StatusChange,
)
from pwm.db.models import Assertion, AssertionRelation, User
from pwm.extraction.factory import build_stages
from pwm.extraction.quotes import normalize
from pwm.pipeline.store import open_record, process_user
from pwm.pipeline.text import visible_body, visible_text

router = APIRouter()
CONTEXT_CHARS = 280


def _source_summary(assertion: Assertion) -> SourceSummary:
    record = open_record(assertion.source.record)
    return SourceSummary(
        kind=record.kind.value,
        sender_name=record.sender.name if record.sender else None,
        sender_address=record.sender.address if record.sender else None,
        subject=record.subject,
        observed_at=record.observed_at,
    )


def _conflicts(session: Session, ids: list[UUID]) -> set[UUID]:
    """Assertions with a live disagreement. A conflict ends when the user dismisses or
    corrects the other side, or a later source replaces it."""
    one, other = aliased(Assertion), aliased(Assertion)
    rows = session.execute(
        select(AssertionRelation.from_id, AssertionRelation.to_id)
        .join(one, AssertionRelation.from_id == one.id)
        .join(other, AssertionRelation.to_id == other.id)
        .where(
            AssertionRelation.type == "contradicts",
            or_(AssertionRelation.from_id.in_(ids), AssertionRelation.to_id.in_(ids)),
            *(
                condition
                for side in (one, other)
                for condition in (
                    side.review.in_(("unreviewed", "confirmed")),
                    side.superseded_by_id.is_(None),
                )
            ),
        )
    )
    return {value for row in rows for value in row}


def item_for(assertion: Assertion, conflicted: set[UUID]) -> CommitmentItem:
    today = clock.today()
    return CommitmentItem(
        id=assertion.id,
        kind=assertion.kind, what=assertion.value, commitment_type=assertion.commitment_type,
        direction=assertion.direction, committed_by=assertion.committed_by,
        committed_to=assertion.committed_to, due=assertion.due,
        overdue=assertion.due is not None and assertion.due < today and assertion.status == "open",
        status=assertion.status, origin=assertion.origin, review=assertion.review,
        confidence=assertion.confidence, evidence_quote=assertion.evidence_quote,
        has_conflict=assertion.id in conflicted, source=_source_summary(assertion),
    )  # fmt: skip


@router.get("/commitments")
def list_commitments(session: DbSession, user: CurrentUser) -> list[CommitmentItem]:
    return needs_attention(session, user)


def needs_attention(session: Session, user: User) -> list[CommitmentItem]:
    """Open commitments not yet dismissed: unreviewed ones to confirm, confirmed ones to do."""
    rows = list(
        session.scalars(
            select(Assertion)
            .where(
                Assertion.user_id == user.id,
                Assertion.kind == "commitment",
                Assertion.superseded_by_id.is_(None),
                Assertion.status == "open",
                Assertion.review.in_(("unreviewed", "confirmed")),
            )  # fmt: skip
            .order_by(Assertion.due.asc().nulls_last(), Assertion.observed_at.desc())
        )
    )
    conflicted = _conflicts(session, [r.id for r in rows])
    return [item_for(row, conflicted) for row in rows]


def _load(session: Session, user: User, assertion_id: UUID) -> Assertion:
    assertion = session.get(Assertion, assertion_id)
    if assertion is None or assertion.user_id != user.id:
        raise HTTPException(404, "not found")
    return assertion


def _context(assertion: Assertion) -> tuple[str, str, str]:
    """The evidence in its surroundings, as (before, quote, after), all normalized the same
    way so the app can highlight the quote without guessing at whitespace or quote marks."""
    record = open_record(assertion.source.record)
    quote = normalize(assertion.evidence_quote)
    text = normalize(visible_body(record))
    if quote not in text:
        text = normalize(visible_text(record))
    at = text.find(quote)
    if at < 0:
        return "", quote, ""
    start, end = max(0, at - CONTEXT_CHARS), min(len(text), at + len(quote) + CONTEXT_CHARS)
    before = ("… " if start else "") + text[start:at]
    after = text[at + len(quote) : end] + (" …" if end < len(text) else "")
    return before, quote, after


def _detail(session: Session, assertion: Assertion) -> AssertionDetail:
    relations = session.execute(
        select(AssertionRelation).where(
            or_(AssertionRelation.from_id == assertion.id, AssertionRelation.to_id == assertion.id)
        )
    ).scalars()
    related = []
    for relation in relations:
        outgoing = relation.from_id == assertion.id
        other = session.get_one(Assertion, relation.to_id if outgoing else relation.from_id)
        if relation.type == "contradicts" and (
            other.review not in ("unreviewed", "confirmed") or other.superseded_by_id is not None
        ):
            continue  # that disagreement has been settled
        label = relation.type if outgoing or relation.type == "contradicts" else "superseded_by"
        related.append(
            RelatedAssertion(
                id=other.id,
                relation=label,
                what=other.value,
                due=other.due,
                evidence_quote=other.evidence_quote,
                source=_source_summary(other),
            )  # fmt: skip
        )
    before, quote, after = _context(assertion)
    item = item_for(assertion, _conflicts(session, [assertion.id]))
    return AssertionDetail(
        **item.model_dump(), subject=assertion.subject,
        predicate=assertion.predicate, extraction_method=assertion.extraction_method,
        recorded_at=assertion.recorded_at, context_before=before, context_quote=quote,
        context_after=after,
        source_suspicious=assertion.source.suspicious, related=related,
    )  # fmt: skip


@router.get("/assertions/{assertion_id}")
def inspect(assertion_id: UUID, session: DbSession, user: CurrentUser) -> AssertionDetail:
    return _detail(session, _load(session, user, assertion_id))


def _apply(session: Session, action: object) -> AssertionDetail:
    try:
        assertion = action()  # type: ignore[operator]
    except LookupError:
        raise HTTPException(404, "not found") from None
    except review.ReviewError as problem:
        raise HTTPException(409, str(problem)) from None
    except DBAPIError:
        session.rollback()
        raise HTTPException(422, "that value cannot be stored") from None
    session.commit()
    return _detail(session, assertion)


@router.post("/assertions/{assertion_id}/confirm")
def confirm(assertion_id: UUID, session: DbSession, user: CurrentUser) -> AssertionDetail:
    return _apply(session, lambda: review.confirm(session, user, assertion_id))


@router.post("/assertions/{assertion_id}/dismiss")
def dismiss(assertion_id: UUID, session: DbSession, user: CurrentUser) -> AssertionDetail:
    def dismiss_and_reread() -> Assertion:
        dismissed = review.dismiss(session, user, assertion_id)
        session.flush()
        # Re-read the mailbox without it: a later genuine update can now take its place.
        process_user(session, user, *build_stages())
        return dismissed

    return _apply(session, dismiss_and_reread)


@router.post("/assertions/{assertion_id}/correct")
def correct(
    assertion_id: UUID, body: Correction, session: DbSession, user: CurrentUser
) -> AssertionDetail:
    return _apply(
        session,
        lambda: review.correct(
            session,
            user,
            assertion_id,
            value=body.what,
            due=body.due,
            clear_due=body.clear_due,
            committed_by=body.committed_by,
            committed_to=body.committed_to,
        ),  # fmt: skip
    )


@router.post("/assertions/{assertion_id}/status")
def set_status(
    assertion_id: UUID, body: StatusChange, session: DbSession, user: CurrentUser
) -> AssertionDetail:
    return _apply(session, lambda: review.set_status(session, user, assertion_id, body.status))
