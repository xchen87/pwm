"""Stages 7-8 and the in-memory world: reconciliation, confidence, and as-of queries.

Everything here is plain code over assertions. The database layer stores the result;
the eval harness reads it directly.
"""

from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel

from pwm.extraction.candidates import Candidate, CandidateKind, Origin
from pwm.pipeline.text import similarity

SAME_SUBJECT = 0.5


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RelationType(StrEnum):
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"


class DraftAssertion(BaseModel):
    """A verified candidate on its way to becoming a stored assertion."""

    candidate: Candidate
    observed_at: datetime
    thread_id: str | None
    sender_address: str | None
    extraction_method: str = ""
    prompt_version: str = ""
    confidence: Confidence = Confidence.MEDIUM
    superseded_by: int | None = None  # index into the same list


class DraftRelation(BaseModel):
    type: RelationType
    from_index: int
    to_index: int


def assign_confidence(
    candidate: Candidate, *, sender_known: bool, sender_is_user: bool, suspicious: bool
) -> Confidence:
    """Coarse and explainable. A model's own certainty is never an input."""
    if candidate.origin is Origin.USER_STATED:
        return Confidence.HIGH
    if suspicious:
        return Confidence.LOW
    trusted = sender_known or sender_is_user
    if candidate.origin is Origin.SOURCE_EXPLICIT:
        return Confidence.HIGH if trusted else Confidence.MEDIUM
    return Confidence.MEDIUM if trusted else Confidence.LOW


def _same_matter(a: Candidate, b: Candidate) -> bool:
    if a.kind != b.kind or a.predicate != b.predicate:
        return False
    if a.kind is CandidateKind.COMMITMENT:
        # Same act, same kind of commitment, same person on the hook. Tom promising to
        # review the numbers does not update Alex's promise to send them.
        same_party = (a.committed_by or "").lower() == (b.committed_by or "").lower()
        return (
            a.commitment_type == b.commitment_type
            and same_party
            and similarity(a.value, b.value) >= SAME_SUBJECT
        )
    return similarity(a.subject, b.subject) >= SAME_SUBJECT


def _differs(a: Candidate, b: Candidate) -> bool:
    if a.kind is CandidateKind.COMMITMENT:
        return a.due is not None and b.due is not None and a.due != b.due
    if a.kind is CandidateKind.DECISION:
        return False
    return a.value.strip().lower() != b.value.strip().lower()


def reconcile(drafts: list[DraftAssertion]) -> list[DraftRelation]:
    """Compare each assertion with earlier ones about the same matter.

    A later statement from the same thread or the same sender is an update and
    supersedes the earlier one. A disagreement between independent sources is a
    contradiction: both stay current and the user is shown both.
    """
    order = sorted(range(len(drafts)), key=lambda i: drafts[i].observed_at)
    relations: list[DraftRelation] = []
    for position, newer_index in enumerate(order):
        newer = drafts[newer_index]
        for older_index in reversed(order[:position]):
            older = drafts[older_index]
            if older.superseded_by is not None or not _same_matter(
                newer.candidate, older.candidate
            ):
                continue
            if not _differs(newer.candidate, older.candidate):
                continue
            same_origin = (newer.thread_id is not None and newer.thread_id == older.thread_id) or (
                newer.sender_address is not None and newer.sender_address == older.sender_address
            )
            if same_origin:
                older.superseded_by = newer_index
                relations.append(
                    DraftRelation(
                        type=RelationType.SUPERSEDES, from_index=newer_index, to_index=older_index
                    )
                )
            else:
                relations.append(
                    DraftRelation(
                        type=RelationType.CONTRADICTS, from_index=newer_index, to_index=older_index
                    )
                )
    return relations


def as_of(drafts: Sequence[DraftAssertion], subject: str, predicate: str, when: date) -> str | None:
    """What the world looked like on `when`, using only what had been observed by then."""
    known = [
        d
        for d in drafts
        if d.candidate.predicate == predicate
        and similarity(d.candidate.subject, subject) >= SAME_SUBJECT
        and d.observed_at.date() <= when
        and (d.candidate.valid_from is None or d.candidate.valid_from <= when)
        and (d.candidate.valid_to is None or d.candidate.valid_to >= when)
    ]
    return max(known, key=lambda d: d.observed_at).candidate.value if known else None
