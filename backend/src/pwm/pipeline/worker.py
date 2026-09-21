"""Postgres-backed job runner. Claims work with SKIP LOCKED so several workers can run safely."""

from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm.db.models import Job, User
from pwm.extraction.interface import Extractor, Triager
from pwm.pipeline.store import process_user

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
    try:
        with session.begin_nested():
            process_user(session, session.get_one(User, job.user_id), triager, extractor)
        job.status = "done"
    except Exception as error:  # noqa: BLE001 - a failed job must be recorded, whatever the cause
        # Validation errors echo their input, which may be message content: keep the type only.
        detail = "" if isinstance(error, ValidationError) else f": {error}"[:300]
        job.last_error = f"{type(error).__name__}{detail}"
        job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "pending"
        job.run_after = datetime.now(UTC) + timedelta(seconds=30 * 2**job.attempts)
    session.commit()
    return True


def run_all(session: Session, triager: Triager, extractor: Extractor) -> int:
    count = 0
    while run_next(session, triager, extractor):
        count += 1
    return count
