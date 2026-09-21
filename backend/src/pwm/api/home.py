from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update

from pwm import clock
from pwm.api.commitments import item_for, needs_attention
from pwm.api.deps import CurrentUser, DbSession
from pwm.api.schemas import CommitmentItem
from pwm.brief import service
from pwm.brief.items import select_items
from pwm.brief.writer import TemplateBriefWriter, WrittenItem
from pwm.db.models import Assertion, Brief, Notification

router = APIRouter()
FIRST_VISIT_LOOKBACK = timedelta(days=14)
NEEDS_ATTENTION_PREVIEW = 3
# Home stays calm: the few changes that matter most, with the rest in the brief.
WHAT_CHANGED_PREVIEW = 4


class Home(BaseModel):
    since: datetime
    what_changed: list[WrittenItem]
    what_changed_total: int
    needs_attention: list[CommitmentItem]
    needs_attention_total: int
    remembered: list[CommitmentItem]
    unread_notifications: int


class BriefView(BaseModel):
    id: UUID
    period: str
    created_at: datetime
    covers_since: datetime
    items: list[WrittenItem]


class NotificationView(BaseModel):
    id: UUID
    title: str
    deep_link: str
    created_at: datetime
    read: bool


class EventIn(BaseModel):
    name: str
    subject_id: UUID | None = None


@router.get("/home")
def home(session: DbSession, user: CurrentUser) -> Home:
    """What changed since the previous visit, what needs attention, and what the user told us."""
    since = user.previous_seen_at or clock.now() - FIRST_VISIT_LOOKBACK
    changes = [
        i for i in select_items(session, user, since, clock.now())
        if i.kind in ("changed", "conflict", "consumer", "remembered")
    ]  # fmt: skip
    attention = needs_attention(session, user)
    remembered = session.scalars(
        select(Assertion)
        .where(
            Assertion.user_id == user.id,
            Assertion.superseded_by_id.is_(None),
            Assertion.kind == "memory",
            Assertion.review != "rejected",
        )  # fmt: skip
        .order_by(Assertion.observed_at.desc())
        .limit(10)
    ).all()
    unread = session.scalars(
        select(Notification.id).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    ).all()
    return Home(
        since=since,
        what_changed=TemplateBriefWriter().write(changes[:WHAT_CHANGED_PREVIEW]),
        what_changed_total=len(changes),
        needs_attention=attention[:NEEDS_ATTENTION_PREVIEW],
        needs_attention_total=len(attention),
        remembered=[item_for(a, set()) for a in remembered],
        unread_notifications=len(unread),
    )


@router.post("/visits")
def record_visit(session: DbSession, user: CurrentUser) -> dict[str, str]:
    """Called when the app comes to the foreground. Moves the "since last visit" marker."""
    now = clock.now()
    # Re-opening the app within the hour is the same visit: it must not wipe "what changed".
    if user.last_seen_at is None or now - user.last_seen_at > timedelta(hours=1):
        user.previous_seen_at = user.last_seen_at
    user.last_seen_at = now
    session.commit()
    return {"status": "ok"}


def _view(brief: Brief) -> BriefView:
    return BriefView(
        id=brief.id,
        period=brief.period,
        created_at=brief.created_at,
        covers_since=brief.covers_since,
        items=service.written_items(brief),
    )


@router.post("/briefs")
def generate_brief(session: DbSession, user: CurrentUser, period: str = "weekly") -> BriefView:
    if period not in service.PERIODS:
        raise HTTPException(422, "period must be daily or weekly")
    brief = service.generate(session, user, TemplateBriefWriter(), service.InboxNotifier(), period)
    session.commit()
    return _view(brief)


@router.get("/briefs/latest")
def latest_brief(session: DbSession, user: CurrentUser) -> BriefView:
    brief = service.latest(session, user)
    if brief is None:
        raise HTTPException(404, "no brief yet")
    return _view(brief)


@router.get("/notifications")
def notifications(session: DbSession, user: CurrentUser) -> list[NotificationView]:
    rows = session.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(20)
    )
    return [
        NotificationView(
            id=n.id,
            title=n.title,
            deep_link=n.deep_link,
            created_at=n.created_at,
            read=n.read_at is not None,
        )  # fmt: skip
        for n in rows
    ]


@router.post("/notifications/read")
def mark_notifications_read(session: DbSession, user: CurrentUser) -> dict[str, str]:
    session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=clock.now())
    )
    session.commit()
    return {"status": "ok"}


@router.post("/events")
def record_event(body: EventIn, session: DbSession, user: CurrentUser) -> dict[str, str]:
    try:
        service.record_event(session, user, body.name, body.subject_id)
    except ValueError as problem:
        raise HTTPException(422, str(problem)) from None
    session.commit()
    return {"status": "ok"}
