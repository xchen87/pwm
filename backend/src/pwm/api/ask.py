from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm import clock, review
from pwm.api.commitments import item_for
from pwm.api.deps import CurrentUser, DbSession
from pwm.api.schemas import CommitmentItem
from pwm.ask.facts import Fact
from pwm.ask.retrieval import retrieve
from pwm.brief.service import record_event
from pwm.db.models import Assertion, AssertionRelation, User
from pwm.extraction.factory import build_stages, build_writers

router = APIRouter()


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class CitedFact(BaseModel):
    assertion_id: UUID
    text: str
    evidence_quote: str
    source_label: str
    is_fact: bool
    confidence: str


class AnswerView(BaseModel):
    text: str
    grounded: bool
    caveat: str | None
    cited: list[CitedFact]


class NewMemory(BaseModel):
    text: str = Field(min_length=2, max_length=2000)


def facts_for(session: Session, user: User) -> list[Fact]:
    rows = session.scalars(
        select(Assertion).where(
            Assertion.user_id == user.id, Assertion.review.in_(("unreviewed", "confirmed"))
        )
    ).all()
    replaced = session.execute(
        select(AssertionRelation.from_id, Assertion.value)
        .join(Assertion, AssertionRelation.to_id == Assertion.id)
        .where(AssertionRelation.user_id == user.id, AssertionRelation.type == "supersedes")
    )
    previous: dict[UUID, str] = {newer: old_value for newer, old_value in replaced}
    facts = []
    for a in rows:
        if a.confidence == "low" and a.review != "confirmed":
            continue  # untrusted messages do not get to answer the user's questions
        sender = a.source.record.get("sender") or {}
        who = sender.get("name") or sender.get("address") or "You"
        subject = a.source.record.get("subject") or "note"
        facts.append(
            Fact(
                id=str(a.id),
                kind=a.kind,
                subject=a.subject,
                predicate=a.predicate,
                value=a.value,
                evidence_quote=a.evidence_quote,
                context_words=f"{subject} {who}",
                source_label=f"{who} · {subject}",
                observed_at=a.observed_at,
                is_fact=a.review == "confirmed" or a.kind == "memory",
                confidence=a.confidence,
                superseded=a.superseded_by_id is not None,
                previous_value=previous.get(a.id),
                commitment_type=a.commitment_type,
                direction=a.direction,
                committed_by=a.committed_by,
                committed_to=a.committed_to,
                due=a.due,
                status=a.status,
            )  # fmt: skip
        )
    return facts


@router.post("/ask")
def ask(body: Question, session: DbSession, user: CurrentUser) -> AnswerView:
    retrieved = retrieve(body.question, facts_for(session, user), clock.today())
    answer = build_writers()[1].answer(body.question, retrieved)
    record_event(session, user, "question_asked")
    session.commit()
    return AnswerView(
        text=answer.text, grounded=answer.grounded, caveat=answer.caveat,
        cited=[
            CitedFact(
                assertion_id=UUID(f.id), text=f.value, evidence_quote=f.evidence_quote,
                source_label=f.source_label, is_fact=f.is_fact, confidence=f.confidence,
            )  # fmt: skip
            for f in answer.cited
        ],
    )  # fmt: skip


@router.post("/memories")
def remember(body: NewMemory, session: DbSession, user: CurrentUser) -> CommitmentItem:
    """Remember this. The note is the user's own statement; anything read out of it
    (a date, a person) still arrives as a possibility."""
    try:
        memory = review.remember(session, user, body.text, *build_stages())
    except ValueError as problem:
        raise HTTPException(422, str(problem)) from None
    session.commit()
    return item_for(memory, set())


@router.delete("/memories/{assertion_id}")
def forget(assertion_id: UUID, session: DbSession, user: CurrentUser) -> dict[str, str]:
    try:
        review.forget(session, user, assertion_id, *build_stages())
    except LookupError:
        raise HTTPException(404, "not found") from None
    session.commit()
    return {"status": "forgotten"}
