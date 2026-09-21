from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from pwm.api.deps import CurrentUser, DbSession
from pwm.brief import service as briefs
from pwm.config import get_settings
from pwm.connectors import service
from pwm.connectors.demo import DemoMailbox
from pwm.db.models import Assertion, Connection, Source, User
from pwm.extraction.factory import build_stages, build_writers
from pwm.pipeline.store import ensure_user
from pwm.sources import Party

router = APIRouter()


class ConnectionView(BaseModel):
    connector: str
    label: str
    connected_at: datetime
    last_synced_at: datetime | None
    # ok | syncing | needs_reconnect | error
    status: str
    sources: int


class Available(BaseModel):
    connector: str
    label: str
    available: bool
    note: str


class ConnectionsView(BaseModel):
    connected: list[ConnectionView]
    available: list[Available]
    understood: int


class SyncResult(BaseModel):
    new_sources: int
    understood: int


def _understood(session: DbSession, user: User) -> int:
    return session.scalar(select(func.count()).where(Assertion.user_id == user.id)) or 0


@router.get("/connections")
def connections(session: DbSession, user: CurrentUser) -> ConnectionsView:
    per_connector = session.execute(
        select(Source.connector, func.count())
        .where(Source.user_id == user.id)
        .group_by(Source.connector)
    )
    counts: dict[str, int] = {name: total for name, total in per_connector}
    rows = session.scalars(select(Connection).where(Connection.user_id == user.id)).all()
    demo_on = get_settings().environment == "local"
    settings = get_settings()
    google_on = settings.google_configured
    waiting = (
        "Read-only. Sign in with Google to connect."
        if google_on
        else "Needs a Google sign-in, which is not set up on this server yet."
    )
    return ConnectionsView(
        connected=[
            ConnectionView(
                connector=c.connector,
                label=c.label,
                connected_at=c.connected_at,
                last_synced_at=c.last_synced_at,
                status=c.status,
                sources=counts.get(c.connector, 0),
            )  # fmt: skip
            for c in rows
        ],
        available=[
            Available(
                connector="gmail", label="Gmail (read-only)", available=google_on, note=waiting
            ),
            Available(
                connector="google_calendar",
                label="Google Calendar (read-only)",
                available=google_on,
                note=waiting,
            ),
            Available(
                connector="demo",
                label=DemoMailbox.label,
                available=demo_on,
                note="An invented person's mail, calendar and notes. Nothing leaves this machine.",
            ),
        ],  # fmt: skip
        understood=_understood(session, user),
    )


@router.post("/connections/demo")
def connect_demo(session: DbSession, user: CurrentUser) -> SyncResult:
    if get_settings().environment != "local":
        raise HTTPException(404, "not available")
    added = service.sync(session, user, DemoMailbox(), *build_stages())
    if added:
        briefs.generate(session, user, build_writers()[0], briefs.InboxNotifier(), "weekly")
    session.commit()
    return SyncResult(new_sources=added, understood=_understood(session, user))


@router.delete("/connections/{connector}")
def disconnect(connector: str, session: DbSession, user: CurrentUser) -> dict[str, int]:
    try:
        removed = service.disconnect(session, user, connector, *build_stages())
    except LookupError:
        raise HTTPException(404, "not connected") from None
    session.commit()
    return {"removed_sources": removed}


class Deleted(BaseModel):
    status: str
    # False when Google could not be reached or our copy of the grant was unreadable. The
    # data here is gone either way; the app then points the user at Google's own
    # "third-party access" page to remove the grant there.
    google_access_revoked: bool


@router.delete("/me")
def delete_everything(session: DbSession, user: CurrentUser) -> Deleted:
    """Delete the user and, by cascade, everything known about them, and withdraw our access
    at Google. A signed-in account is simply gone; the local development identity starts
    again empty, because that is all "signing up again" means for it."""
    revoked = service.revoke_google(session, user)
    was_dev_user = user.google_sub is None
    identity = Party(name=user.name, address=user.email)
    session.execute(delete(User).where(User.id == user.id))
    session.expire_all()
    if was_dev_user:
        ensure_user(session, identity)
    session.commit()
    return Deleted(status="deleted", google_access_revoked=revoked)
