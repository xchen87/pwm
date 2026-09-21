from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from pwm import review
from pwm.api.deps import CurrentUser, DbSession
from pwm.db.models import Person
from pwm.extraction.factory import build_stages
from pwm.pipeline.store import process_user

router = APIRouter()


class IdentifierView(BaseModel):
    id: UUID
    address: str
    # exact: seen as such. inferred: my guess, which you can confirm or reject. user: you said so.
    link: str


class PersonView(BaseModel):
    id: UUID
    name: str
    identifiers: list[IdentifierView]


class NotThem(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.get("/people")
def people(session: DbSession, user: CurrentUser) -> list[PersonView]:
    rows = session.scalars(
        select(Person).where(Person.user_id == user.id).order_by(Person.display_name)
    )
    return [
        PersonView(
            id=p.id,
            name=p.display_name,
            identifiers=[
                IdentifierView(id=i.id, address=i.value, link=i.link)
                for i in sorted(p.identifiers, key=lambda i: i.value)
            ],
        )
        for p in rows
    ]


@router.post("/people/identifiers/{identifier_id}/confirm")
def same_person(identifier_id: UUID, session: DbSession, user: CurrentUser) -> dict[str, str]:
    """Yes, this address is that person. Facts are re-read with that in mind: what looked
    like a disagreement between two people may turn out to be one person's update."""
    try:
        review.confirm_link(session, user, identifier_id)
    except LookupError:
        raise HTTPException(404, "not found") from None
    session.flush()
    process_user(session, user, *build_stages())
    session.commit()
    return {"status": "confirmed"}


@router.post("/people/identifiers/{identifier_id}/split")
def different_person(
    identifier_id: UUID, body: NotThem, session: DbSession, user: CurrentUser
) -> dict[str, str]:
    try:
        review.split_identifier(session, user, identifier_id, body.name.strip())
    except LookupError:
        raise HTTPException(404, "not found") from None
    session.flush()
    process_user(session, user, *build_stages())
    session.commit()
    return {"status": "split"}
