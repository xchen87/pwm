"""Generating, storing, and announcing briefs."""

from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pwm import clock
from pwm.brief.items import select_items
from pwm.brief.writer import BriefWriter, WrittenItem
from pwm.db.models import Brief, Notification, ProductEvent, User

PERIODS = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
# Fixed, generic, and free of personal content: lock screens and push services see this.
BRIEF_READY_TITLE = "Your World Brief is ready"


class Notifier(Protocol):
    def notify(self, session: Session, user: User, title: str, deep_link: str) -> None: ...


class InboxNotifier:
    """Local stand-in for push: records the notification in the in-app inbox.

    Real push (Slice 5) implements the same interface and sends the same generic title.
    """

    channel = "inbox"

    def notify(self, session: Session, user: User, title: str, deep_link: str) -> None:
        session.add(
            Notification(
                user_id=user.id,
                title=title,
                deep_link=deep_link,
                channel=self.channel,
                created_at=clock.now(),
            )  # fmt: skip
        )


def generate(
    session: Session, user: User, writer: BriefWriter, notifier: Notifier, period: str = "daily",
    since: datetime | None = None,
) -> Brief:  # fmt: skip
    now = clock.now()
    covers_since = since or now - PERIODS[period]
    written = writer.write(select_items(session, user, covers_since, now))
    brief = Brief(
        user_id=user.id, period=period, covers_since=covers_since, writer_version=writer.version,
        items=[w.model_dump(mode="json") for w in written], created_at=now,
    )  # fmt: skip
    session.add(brief)
    session.flush()
    unread = session.scalar(
        select(func.count()).where(
            Notification.user_id == user.id,
            Notification.title == BRIEF_READY_TITLE,
            Notification.read_at.is_(None),
        )
    )
    # An empty brief is not worth a notification, and neither is a second "ready" while the
    # first is still unread.
    if written and not unread:
        notifier.notify(session, user, BRIEF_READY_TITLE, f"pwm://brief/{brief.id}")
    return brief


def latest(session: Session, user: User) -> Brief | None:
    return session.scalar(
        select(Brief)
        .where(Brief.user_id == user.id)
        .order_by(Brief.created_at.desc(), Brief.period.desc())
        .limit(1)
    )


def written_items(brief: Brief) -> list[WrittenItem]:
    return [WrittenItem.model_validate(item) for item in brief.items]


EVENT_NAMES = {
    "brief_opened", "item_useful", "item_not_useful", "item_dismissed", "item_corrected",
    "item_acted", "notification_opened", "source_inspected", "question_asked",
    "export_requested", "export_downloaded",
}  # fmt: skip


def record_event(session: Session, user: User, name: str, subject_id: object = None) -> None:
    if name not in EVENT_NAMES:
        raise ValueError(f"unknown event: {name}")
    session.add(
        ProductEvent(user_id=user.id, name=name, subject_id=subject_id, created_at=clock.now())
    )


def generate_due(session: Session, writer: BriefWriter, notifier: Notifier) -> int:
    """Generate a brief for every user whose last one of that period is older than the
    period. Meant to be run on a schedule; running it more often changes nothing."""
    now = clock.now()
    made = 0
    for user in session.scalars(select(User)):
        for period, length in PERIODS.items():
            last = session.scalar(
                select(Brief.created_at)
                .where(Brief.user_id == user.id, Brief.period == period)
                .order_by(Brief.created_at.desc())
                .limit(1)
            )
            if last is not None and now - last < length:
                continue
            try:
                with session.begin_nested():
                    brief = generate(session, user, writer, notifier, period)
            except Exception:  # noqa: BLE001 - one user's failure must not stop everyone's briefs
                continue
            if not brief.items:
                session.delete(brief)  # nothing to say is not a brief
                continue
            made += 1
    return made
