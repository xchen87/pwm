"""User decisions about assertions and people.

This module is the only code that writes `Assertion.review`, and it is reachable only
from authenticated API calls made by the user. Every action leaves a ReviewEvent.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pwm.db.models import (
    Assertion,
    AssertionRelation,
    Person,
    PersonIdentifier,
    ReviewEvent,
    User,
)

COMMITMENT_STATUSES = {"open", "done", "cancelled"}


class ReviewError(Exception):
    """The requested action does not apply to this assertion in its current state."""


def _owned(session: Session, user: User, assertion_id: UUID) -> Assertion:
    assertion = session.get(Assertion, assertion_id)
    if assertion is None or assertion.user_id != user.id:
        raise LookupError(str(assertion_id))
    return assertion


def _log(session: Session, user: User, assertion: Assertion, action: str, **detail: object) -> None:
    session.add(
        ReviewEvent(user_id=user.id, assertion_id=assertion.id, action=action, detail=detail)
    )


def confirm(session: Session, user: User, assertion_id: UUID) -> Assertion:
    assertion = _owned(session, user, assertion_id)
    if assertion.superseded_by_id is not None:
        raise ReviewError("this has been replaced by a newer assertion")
    assertion.review = "confirmed"
    _log(session, user, assertion, "confirm")
    return assertion


def dismiss(session: Session, user: User, assertion_id: UUID) -> Assertion:
    assertion = _owned(session, user, assertion_id)
    assertion.review = "rejected"
    _log(session, user, assertion, "dismiss")
    return assertion


def correct(
    session: Session, user: User, assertion_id: UUID, *,
    value: str | None = None, due: date | None = None, clear_due: bool = False,
    committed_by: str | None = None, committed_to: str | None = None,
) -> Assertion:  # fmt: skip
    """Record what the user says is true. The original is kept, marked corrected, and superseded."""
    original = _owned(session, user, assertion_id)
    if original.superseded_by_id is not None:
        raise ReviewError("this has already been replaced")
    corrected = Assertion(
        user_id=user.id, source_id=original.source_id, kind=original.kind,
        subject=original.subject, predicate=original.predicate,
        value=value if value is not None else original.value,
        # Provenance is retained: the correction still points at the evidence that prompted it.
        evidence_quote=original.evidence_quote,
        extraction_method="user_correction", prompt_version=f"of:{original.id}",
        origin="user_stated", review="confirmed", confidence="high",
        valid_from=original.valid_from, valid_to=original.valid_to,
        observed_at=datetime.now(UTC),
        commitment_type=original.commitment_type, direction=original.direction,
        committed_by=committed_by if committed_by is not None else original.committed_by,
        committed_to=committed_to if committed_to is not None else original.committed_to,
        due=None if clear_due else (due if due is not None else original.due),
        status=original.status,
    )  # fmt: skip
    session.add(corrected)
    session.flush()
    original.review = "corrected"
    original.superseded_by_id = corrected.id
    session.add(
        AssertionRelation(
            user_id=user.id, type="supersedes", from_id=corrected.id, to_id=original.id
        )
    )
    _log(session, user, original, "correct", replaced_by=str(corrected.id))
    return corrected


def set_status(session: Session, user: User, assertion_id: UUID, status: str) -> Assertion:
    assertion = _owned(session, user, assertion_id)
    if assertion.kind != "commitment" or status not in COMMITMENT_STATUSES:
        raise ReviewError("only commitments have a status of open, done, or cancelled")
    if assertion.review != "confirmed":
        raise ReviewError("confirm the commitment before tracking its status")
    assertion.status = status
    _log(session, user, assertion, "set_status", status=status)
    return assertion


def _person(session: Session, user: User, person_id: UUID) -> Person:
    person = session.get(Person, person_id)
    if person is None or person.user_id != user.id:
        raise LookupError(str(person_id))
    return person


def merge_people(session: Session, user: User, keep_id: UUID, absorb_id: UUID) -> Person:
    keep, absorb = _person(session, user, keep_id), _person(session, user, absorb_id)
    if keep.id == absorb.id:
        raise ReviewError("cannot merge a person with themselves")
    session.execute(
        update(PersonIdentifier)
        .where(PersonIdentifier.person_id == absorb.id)
        .values(person_id=keep.id, link="user")
    )
    # Reload so deleting the emptied person does not cascade to the moved identifiers.
    session.refresh(absorb)
    session.delete(absorb)
    session.flush()
    session.refresh(keep)
    return keep


def split_identifier(session: Session, user: User, identifier_id: UUID, name: str) -> Person:
    """Undo a wrong link: move one address to a new person. Code never re-merges it."""
    identifier = session.scalar(
        select(PersonIdentifier).where(
            PersonIdentifier.id == identifier_id, PersonIdentifier.user_id == user.id
        )
    )
    if identifier is None:
        raise LookupError(str(identifier_id))
    person = Person(user_id=user.id, display_name=name)
    session.add(person)
    session.flush()
    identifier.person_id, identifier.link = person.id, "user"
    return person


def rename_person(session: Session, user: User, person_id: UUID, name: str) -> Person:
    person = _person(session, user, person_id)
    person.display_name = name
    return person
