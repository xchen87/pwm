"""Connecting, syncing, and disconnecting data sources."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pwm import clock
from pwm.connectors.base import Connector
from pwm.db.models import Connection, Source, User
from pwm.extraction.interface import Extractor, Triager
from pwm.pipeline.store import ingest, process_user


def sync(
    session: Session, user: User, connector: Connector, triager: Triager, extractor: Extractor
) -> int:
    """Connect if needed, pull what is new, and process it. Safe to repeat."""
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
    records = list(connector.fetch(connection.cursor))
    added = ingest(session, user, records, connector=connector.name)
    if records:
        connection.cursor = max(r.observed_at for r in records)
    connection.last_synced_at = clock.now()
    if added:
        process_user(session, user, triager, extractor)
    return added


def disconnect(
    session: Session, user: User, connector: str, triager: Triager, extractor: Extractor
) -> int:
    """Remove the connection and everything it brought in, then rebuild what is left."""
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
    session.expire_all()
    process_user(session, user, triager, extractor)
    return len(removed)
