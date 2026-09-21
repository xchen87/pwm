"""Connecting, syncing, and disconnecting data sources."""

from sqlalchemy import delete, select
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


def sync(
    session: Session, user: User, connector: Connector, triager: Triager, extractor: Extractor
) -> int:
    """Connect if needed, pull the next batch, and process it. Safe to repeat.

    One batch per call: on a first sync that is the newest page, which is processed and
    visible before older pages are fetched. If there is more, a follow-up job is queued.
    """
    connection = connection_for(session, user, connector)
    try:
        result = connector.fetch(connection.cursor)
    except GrantRevoked:
        # The user revoked access at Google, or the grant expired. Not an error to retry:
        # the app asks them to reconnect.
        connection.status, connection.last_error = "needs_reconnect", "GrantRevoked"
        return 0
    added = ingest(session, user, result.records, connector=connector.name, enqueue_job=False)
    connection.cursor = result.cursor
    connection.last_synced_at = clock.now()
    connection.status, connection.last_error = ("syncing" if result.more else "ok"), None
    if added:
        process_user(session, user, triager, extractor)
    if result.more:
        session.add(Job(user_id=user.id, kind="sync", key=connector.name))
    return added


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
    session.flush()
    if connector in GOOGLE_CONNECTORS:
        revoke_google_if_unused(session, user)
    session.expire_all()
    process_user(session, user, triager, extractor)
    return len(removed)


def revoke_google(session: Session, user: User) -> None:
    """Withdraw our access at Google and destroy the stored token, unconditionally."""
    session.execute(
        delete(Connection).where(
            Connection.user_id == user.id, Connection.connector.in_(GOOGLE_CONNECTORS)
        )
    )
    revoke_google_if_unused(session, user)


def revoke_google_if_unused(
    session: Session, user: User, client: GoogleClient | None = None
) -> None:
    still_used = session.scalar(
        select(Connection.id).where(
            Connection.user_id == user.id, Connection.connector.in_(GOOGLE_CONNECTORS)
        )
    )
    stored = session.scalar(
        select(OAuthToken).where(OAuthToken.user_id == user.id, OAuthToken.provider == "google")
    )
    if still_used or stored is None:
        return
    try:
        token = crypto.decrypt(stored.refresh_token_encrypted, "google-refresh")
        (client or google_client()).revoke(token)
    except (crypto.Undecryptable, crypto.DataKeyMissing):
        pass  # unreadable here means unusable anywhere; destroying it is still right
    session.delete(stored)
