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
from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pwm import clock, crypto
from pwm.api.deps import CurrentUser, DbSession
from pwm.brief.service import record_event
from pwm.config import get_settings
from pwm.db.models import (
    Assertion,
    AssertionRelation,
    AuthSession,
    Brief,
    Connection,
    Device,
    ExportCode,
    ModelCall,
    Notification,
    Person,
    ProductEvent,
    ReviewEvent,
    Source,
    StageResult,
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
    record_event(session, user, "export_requested")  # a full download is worth a trace
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
        except ValidationError:
            record["record_note"] = "stored in an older form; given as stored"
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
            "last_seen_at": user.last_seen_at,
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
                "id": str(p.id),
                "name": p.display_name,
                "addresses": [{"address": i.value, "link": i.link} for i in p.identifiers],
            }
            for p in rows(Person, Person.display_name)
        ],
        # What the reading stages concluded about each source, and what each call cost.
        "stage_results": [
            {
                "source_id": str(r.source_id),
                "stage": r.stage,
                "version": r.version,
                "result": r.result,
            }
            for r in rows(StageResult, StageResult.created_at)
        ],
        "model_calls": [
            {
                "source_id": str(c.source_id) if c.source_id else None,
                "stage": c.stage,
                "model": c.model,
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "at": c.created_at,
            }
            for c in rows(ModelCall, ModelCall.created_at)
        ],
        "sessions": [
            {"created_at": s.created_at, "expires_at": s.expires_at, "revoked_at": s.revoked_at}
            for s in rows(AuthSession, AuthSession.created_at)
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
            {
                "id": str(b.id),
                "period": b.period,
                "covers_since": b.covers_since,
                "created_at": b.created_at,
                "items": b.items,
            }
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
    # DELETE ... RETURNING: exactly one request can ever win the row, however many race for it.
    spent = session.execute(
        delete(ExportCode)
        .where(ExportCode.code_hash == _hash(code))
        .returning(ExportCode.user_id, ExportCode.expires_at)
    ).first()
    session.commit()
    if spent is None or spent.expires_at < clock.now():
        raise HTTPException(404, "this export link is not valid; ask for a new one in the app")
    user = session.get(User, spent.user_id)
    if user is None:
        raise HTTPException(404, "this export link is not valid; ask for a new one in the app")
    record_event(session, user, "export_downloaded")
    session.commit()
    payload = build_export(session, user)
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(
        jsonable_encoder(payload),
        headers={"Content-Disposition": 'attachment; filename="your-world-export.json"'},
    )
