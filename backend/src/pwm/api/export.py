"""Everything we hold about a person, as one file they can keep.

Two steps, so that no bearer token ever sits in a URL: the app asks for a single-use code,
then opens the download in the system browser with that code. The export is built from the
same tables the product reads, with encrypted bodies opened, and with nothing that is not
theirs: no tokens, no other users, no internal ids beyond those needed to relate rows.
"""

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pwm import clock, crypto
from pwm.api.deps import CurrentUser, DbSession
from pwm.config import get_settings
from pwm.db.models import (
    Assertion,
    AssertionRelation,
    Brief,
    Connection,
    Device,
    ExportCode,
    Notification,
    Person,
    ProductEvent,
    ReviewEvent,
    Source,
    User,
)
from pwm.pipeline.store import open_record

router = APIRouter()


class ExportTicket(BaseModel):
    url: str
    expires_in_seconds: int


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@router.post("/me/export")
def request_export(session: DbSession, user: CurrentUser) -> ExportTicket:
    settings = get_settings()
    now = clock.now()
    session.execute(delete(ExportCode).where(ExportCode.expires_at < now))
    code = secrets.token_urlsafe(32)
    lifetime = timedelta(minutes=settings.export_code_minutes)
    session.add(ExportCode(code_hash=_hash(code), user_id=user.id, expires_at=now + lifetime))
    session.commit()
    return ExportTicket(
        url=f"{settings.public_url.rstrip('/')}/me/export/{code}",
        expires_in_seconds=int(lifetime.total_seconds()),
    )


def build_export(session: Session, user: User) -> dict[str, Any]:
    def rows(model: type, order: Any) -> list[Any]:
        return list(session.scalars(select(model).where(model.user_id == user.id).order_by(order)))  # type: ignore[attr-defined]

    def source(s: Source) -> dict[str, Any]:
        record: dict[str, Any] = dict(s.record)
        try:
            record = open_record(record).model_dump(mode="json")
        except (crypto.DataKeyMissing, crypto.Undecryptable):
            record["body"] = None
            record["body_unavailable"] = "encrypted under a key this server no longer holds"
        return {"id": str(s.id), "connector": s.connector, **record}

    def assertion(a: Assertion) -> dict[str, Any]:
        return {
            "id": str(a.id), "source_id": str(a.source_id), "kind": a.kind, "subject": a.subject,
            "predicate": a.predicate, "value": a.value, "evidence_quote": a.evidence_quote,
            "origin": a.origin, "review": a.review, "confidence": a.confidence,
            "extraction_method": a.extraction_method, "valid_from": a.valid_from,
            "valid_to": a.valid_to, "observed_at": a.observed_at, "recorded_at": a.recorded_at,
            "superseded_by_id": str(a.superseded_by_id) if a.superseded_by_id else None,
            "commitment_type": a.commitment_type, "direction": a.direction,
            "committed_by": a.committed_by, "committed_to": a.committed_to, "due": a.due,
            "status": a.status,
        }  # fmt: skip

    return {
        "format": "personal-world-model-export/1",
        "exported_at": clock.now(),
        "account": {
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at,
            "terms_version": user.terms_version,
            "terms_accepted_at": user.terms_accepted_at,
            "age_attested_at": user.age_attested_at,
        },  # fmt: skip
        "connections": [
            {
                "connector": c.connector,
                "label": c.label,
                "connected_at": c.connected_at,
                "last_synced_at": c.last_synced_at,
                "status": c.status,
            }
            for c in rows(Connection, Connection.connected_at)
        ],  # fmt: skip
        "sources": [source(s) for s in rows(Source, Source.observed_at)],
        "assertions": [assertion(a) for a in rows(Assertion, Assertion.observed_at)],
        "relations": [
            {"type": r.type, "from_id": str(r.from_id), "to_id": str(r.to_id), "made_by": r.made_by}
            for r in rows(AssertionRelation, AssertionRelation.type)
        ],
        "people": [
            {
                "name": p.display_name,
                "addresses": [{"address": i.value, "link": i.link} for i in p.identifiers],
            }
            for p in rows(Person, Person.display_name)
        ],
        "reviews": [
            {
                "assertion_id": str(e.assertion_id),
                "action": e.action,
                "detail": e.detail,
                "at": e.created_at,
            }
            for e in rows(ReviewEvent, ReviewEvent.created_at)
        ],
        "briefs": [
            {"id": str(b.id), "period": b.period, "created_at": b.created_at, "items": b.items}
            for b in rows(Brief, Brief.created_at)
        ],
        "notifications": [
            {
                "title": n.title,
                "deep_link": n.deep_link,
                "channel": n.channel,
                "created_at": n.created_at,
                "read_at": n.read_at,
            }
            for n in rows(Notification, Notification.created_at)
        ],
        "usage_events": [
            {
                "name": e.name,
                "subject_id": str(e.subject_id) if e.subject_id else None,
                "at": e.created_at,
            }
            for e in rows(ProductEvent, ProductEvent.created_at)
        ],
        "devices": [
            {"platform": d.platform, "registered_at": d.registered_at}
            for d in rows(Device, Device.registered_at)
        ],
    }


@router.get("/me/export/{code}")
def download_export(code: str, session: DbSession) -> JSONResponse:
    row = session.get(ExportCode, _hash(code))
    if row is not None:
        session.delete(row)
        session.commit()
    if row is None or row.expires_at < clock.now():
        raise HTTPException(404, "this export link is not valid; ask for a new one in the app")
    user = session.get(User, row.user_id)
    if user is None:
        raise HTTPException(404, "this export link is not valid; ask for a new one in the app")
    payload = build_export(session, user)
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(
        jsonable_encoder(payload),
        headers={"Content-Disposition": 'attachment; filename="your-world-export.json"'},
    )
