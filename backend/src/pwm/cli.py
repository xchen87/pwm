"""Local development commands.

uv run python -m pwm.cli demo    # load the synthetic fixture for the local user and process it
uv run python -m pwm.cli work       # run any pending jobs
uv run python -m pwm.cli reprocess  # run the funnel again over everything (idempotent)
uv run python -m pwm.cli brief      # generate a weekly World Brief for the local user
uv run python -m pwm.cli tick       # scheduled work: pending jobs, then any briefs that are due
uv run python -m pwm.cli reset   # delete the local user and everything derived from them
"""

import argparse

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pwm.brief.service import InboxNotifier, generate, generate_due
from pwm.brief.writer import TemplateBriefWriter
from pwm.config import get_settings
from pwm.connectors.demo import DemoMailbox
from pwm.connectors.service import sync
from pwm.db.models import User
from pwm.db.session import get_engine
from pwm.extraction.factory import build_stages
from pwm.pipeline.store import ensure_user, process_user
from pwm.pipeline.worker import run_all
from pwm.sources import Party


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["demo", "work", "reprocess", "brief", "tick", "reset"])
    command = parser.parse_args().command
    settings = get_settings()

    with Session(get_engine()) as session:
        if command == "reset":
            session.execute(delete(User).where(User.email == settings.dev_user_email))
            session.commit()
            print("local user and all derived data deleted")
            return
        if command == "demo":
            user = ensure_user(
                session, Party(name=settings.dev_user_name, address=settings.dev_user_email)
            )
            added = sync(session, user, DemoMailbox(), *build_stages())
            session.commit()
            print(f"ingested {added} new sources")
            return
        if command == "brief":
            user = session.scalars(select(User).where(User.email == settings.dev_user_email)).one()
            brief = generate(session, user, TemplateBriefWriter(), InboxNotifier(), "weekly")
            session.commit()
            print(f"brief {brief.id}: {len(brief.items)} item(s)")
            return
        triager, extractor = build_stages()
        if command == "tick":
            jobs = run_all(session, triager, extractor)
            briefs = generate_due(session, TemplateBriefWriter(), InboxNotifier())
            session.commit()
            print(f"ran {jobs} job(s), made {briefs} brief(s)")
            return
        if command == "reprocess":
            for user in session.scalars(select(User)):
                process_user(session, user, triager, extractor)
            session.commit()
            print("reprocessed")
            return
        print(f"ran {run_all(session, triager, extractor)} job(s) with {extractor.method}")


if __name__ == "__main__":
    main()
