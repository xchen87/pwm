"""Connecting, syncing, and disconnecting data sources."""

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from pwm import clock, crypto
from pwm.config import get_settings
from pwm.connectors.base import Connector
from pwm.connectors.demo import DemoMailbox
from pwm.db.models import Connection, Job, OAuthToken, Source, User
from pwm.extraction.interface import Extractor, Triager
from pwm.google.http import GoogleClient, GrantRevoked
from pwm.pipeline.store import ingest, process_user
from pwm.sources import Party

GOOGLE_CONNECTORS = ("gmail", "google_calendar")
ERROR_RETRY = timedelta(hours=6)
PROCESS_EVERY = 10


def google_client() -> GoogleClient:
    """The one place a GoogleClient is made for background work, so tests can swap it."""
    return GoogleClient(get_settings())


def connection_for(session: Session, user: User, connector: Connector) -> Connection:
    connection = session.scalar(
        select(Connection).where(
            Connection.user_id == user.id, Connection.connector == connector.name
        )
    )
    if connection is None:
        connection = Connection(
            user_id=user.id, connector=connector.name, label=connector.label,
            connected_at=clock.now(),
        )  # fmt: skip
        session.add(connection)
    return connection


def lock_user(session: Session, user: User) -> None:
    """One writer per user at a time, for the rest of this transaction. Syncing,
    disconnecting and rebuilding all take it first, so none sees another's half-done work.
    (Same lock as `process_user`; it is re-entrant within a session.)"""
    session.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(user.id)))))


def enqueue_sync(session: Session, user: User, connector: str) -> None:
    """At most one pending sync per connection: two would fetch the same page twice."""
    pending = session.scalar(
        select(Job.id).where(
            Job.user_id == user.id,
            Job.kind == "sync",
            Job.key == connector,
            Job.status == "pending",
        )
    )
    if pending is None:
        session.add(Job(user_id=user.id, kind="sync", key=connector))


def sync(
    session: Session,
    user: User,
    connector: Connector,
    triager: Triager,
    extractor: Extractor,
    create: bool = True,
) -> int:
    """Pull the next batch for a connection and process it. Safe to repeat.

    One batch per call: on a first sync that is the newest page, which is processed and
    visible before older pages are fetched. If there is more, a follow-up job is queued.

    Background jobs pass `create=False`: a job left over from before the user disconnected
    must do nothing. Only the user connecting creates a connection.
    """
    lock_user(session, user)
    if create:
        connection = connection_for(session, user, connector)
    else:
        found = session.scalar(
            select(Connection).where(
                Connection.user_id == user.id, Connection.connector == connector.name
            )
        )
        if found is None:
            return 0
        connection = found
    try:
        result = connector.fetch(connection.cursor)
    except GrantRevoked:
        # The user revoked access at Google, or the grant expired. Not an error to retry:
        # the app asks them to reconnect.
        connection.status, connection.last_error = "needs_reconnect", "GrantRevoked"
        return 0
    added = ingest(session, user, result.records, connector=connector.name, enqueue_job=False)
    page = int(connection.pages_synced or 0) + 1
    connection.pages_synced = 0 if not result.more else page
    connection.unprocessed = int(connection.unprocessed or 0) + added
    connection.cursor = result.cursor
    connection.last_synced_at = clock.now()
    connection.status, connection.last_error = ("syncing" if result.more else "ok"), None
    # Rebuilding the world is a whole-mailbox pass. During a long first read it runs on the
    # first page (something to see within minutes), every tenth page, and the last; not on
    # every page, which would make a 90-day read quadratic. What counts is whether anything
    # is *waiting*, not whether this page added it: a last page that adds nothing still
    # owes a rebuild for the pages before it.
    if connection.unprocessed and (not result.more or page == 1 or page % PROCESS_EVERY == 0):
        process_user(session, user, triager, extractor)
        connection.unprocessed = 0
    if result.more:
        enqueue_sync(session, user, connector.name)
    return added


def enqueue_due_syncs(session: Session) -> int:
    """Queue a sync for every healthy connection not synced recently. Run on a schedule:
    this is what keeps the world current after the first read."""
    now = clock.now()
    cutoff = now - timedelta(minutes=get_settings().sync_minutes)
    due = [
        c
        for c in session.scalars(
            select(Connection).where(
                Connection.connector.in_(GOOGLE_CONNECTORS), Connection.status.in_(("ok", "error"))
            )
        )
        # A connection that failed for good is tried again a few times a day, not every tick.
        if c.last_synced_at is None
        or c.last_synced_at < (now - ERROR_RETRY if c.status == "error" else cutoff)
    ]
    for connection in due:
        user = session.get_one(User, connection.user_id)
        enqueue_sync(session, user, connection.connector)
    return len(due)


def mark_sync_failed(session: Session, user: User, connector: str, error: str) -> None:
    connection = session.scalar(
        select(Connection).where(Connection.user_id == user.id, Connection.connector == connector)
    )
    if connection is not None:
        connection.status, connection.last_error = "error", error
        connection.last_synced_at = clock.now()  # the clock the retry back-off runs on


def build_connector(session: Session, user: User, name: str) -> Connector:
    """The connector for one of the user's connections, with its credentials loaded."""
    if name == DemoMailbox.name:
        return DemoMailbox()
    if name not in GOOGLE_CONNECTORS:
        raise LookupError(name)
    from pwm.connectors.gcalendar import CalendarConnector
    from pwm.connectors.gmail import GmailConnector
    from pwm.google.account import GoogleAccount

    stored = session.scalar(
        select(OAuthToken).where(OAuthToken.user_id == user.id, OAuthToken.provider == "google")
    )
    if stored is None:
        raise LookupError(name)
    settings = get_settings()
    account = GoogleAccount(
        google_client(), crypto.decrypt(stored.refresh_token_encrypted, "google-refresh")
    )
    if name == "gmail":
        return GmailConnector(account, settings.backfill_days)
    owner = Party(name=user.name, address=user.email)
    return CalendarConnector(account, owner, settings.backfill_days)


def disconnect(
    session: Session, user: User, connector: str, triager: Triager, extractor: Extractor
) -> int:
    """Remove the connection and everything it brought in, then rebuild what is left.

    When the last Google connection goes, the grant is revoked at Google and the stored
    refresh token is destroyed, whether or not Google could be reached.
    """
    # Wait for any sync of this user's data that is in flight, *then* look. Otherwise a page
    # a worker is in the middle of writing is invisible here, and survives the disconnect.
    lock_user(session, user)
    connection = session.scalar(
        select(Connection).where(Connection.user_id == user.id, Connection.connector == connector)
    )
    if connection is None:
        raise LookupError(connector)
    removed = session.execute(
        delete(Source)
        .where(Source.user_id == user.id, Source.connector == connector)
        .returning(Source.id)
    ).all()
    session.delete(connection)
    # A queued page of a backfill must not bring back what the user just removed.
    session.execute(
        delete(Job).where(
            Job.user_id == user.id,
            Job.kind == "sync",
            Job.key == connector,
            Job.status == "pending",
        )
    )
    session.flush()
    if connector in GOOGLE_CONNECTORS:
        revoke_google_if_unused(session, user)
    session.expire_all()
    process_user(session, user, triager, extractor)
    return len(removed)


def revoke_google(session: Session, user: User) -> bool:
    """Withdraw our access at Google and destroy the stored token, unconditionally.
    Returns whether Google confirmed; the token is destroyed here either way."""
    session.execute(
        delete(Connection).where(
            Connection.user_id == user.id, Connection.connector.in_(GOOGLE_CONNECTORS)
        )
    )
    return revoke_google_if_unused(session, user)


def revoke_google_if_unused(
    session: Session, user: User, client: GoogleClient | None = None
) -> bool:
    """True when nothing is left alive at Google (revoked, or there was never a token)."""
    still_used = session.scalar(
        select(Connection.id).where(
            Connection.user_id == user.id, Connection.connector.in_(GOOGLE_CONNECTORS)
        )
    )
    stored = session.scalar(
        select(OAuthToken).where(OAuthToken.user_id == user.id, OAuthToken.provider == "google")
    )
    if still_used or stored is None:
        return True
    try:
        token = crypto.decrypt(stored.refresh_token_encrypted, "google-refresh")
        confirmed = (client or google_client()).revoke(token)
    except (crypto.Undecryptable, crypto.DataKeyMissing):
        # We cannot read our own copy, so we cannot ask Google to revoke it. The copy is
        # destroyed; the user is told to remove access on Google's side themselves.
        confirmed = False
    session.delete(stored)
    return confirmed
