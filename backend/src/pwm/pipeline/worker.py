"""Postgres-backed job runner. Claims work with SKIP LOCKED so several workers can run safely."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm.config import get_settings
from pwm.db.models import Job, User
from pwm.extraction.interface import Extractor, Triager
from pwm.pipeline.store import StageCache, process_user

MAX_ATTEMPTS = 5


def run_next(session: Session, triager: Triager, extractor: Extractor) -> bool:
    """Run one pending job. Returns False when the queue is empty."""
    job = session.scalar(
        select(Job)
        .where(Job.status == "pending", Job.run_after <= datetime.now(UTC))
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return False
    job.attempts += 1
    # Not "pending" while it runs, so that a follow-up page queued from inside this job is not
    # mistaken for a duplicate of it. This is only ever visible within this transaction: a
    # worker that dies rolls back, and the job is pending again.
    job.status = "running"
    user = session.get_one(User, job.user_id)
    caches: list[StageCache] = []
    try:
        with session.begin_nested():
            if job.kind == "sync" and user.terms_version != get_settings().terms_version:
                pass  # nothing is read for an account that has not agreed to the current terms
            elif job.kind == "sync":
                # Imported here: connectors depend on the store, not the other way round.
                from pwm.connectors.service import build_connector, sync

                connector = build_connector(session, user, job.key)
                sync(session, user, connector, triager, extractor, create=False)
            else:
                process_user(session, user, triager, extractor, caches)
        job.status = "done"
    except Exception as error:  # noqa: BLE001 - a failed job must be recorded, whatever the cause
        # The rollback above also discarded the model results and audit rows of calls that
        # really happened. Put them back so a retry does not pay for them again.
        for cache in caches:
            cache.replay()
        # Exception text routinely echoes its input (constraint violations quote the row,
        # validation errors quote the value), and the input here is someone's mail.
        job.last_error = type(error).__name__
        job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "pending"
        if job.kind == "sync" and job.status == "failed":
            from pwm.connectors.service import mark_sync_failed

            # Tell the user, instead of leaving "still reading" on screen forever.
            mark_sync_failed(session, user, job.key, type(error).__name__)
        job.run_after = datetime.now(UTC) + timedelta(seconds=30 * 2**job.attempts)
    session.commit()
    return True


def run_all(session: Session, triager: Triager, extractor: Extractor) -> int:
    count = 0
    while run_next(session, triager, extractor):
        count += 1
    return count
