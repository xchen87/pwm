"""Local development commands.

uv run python -m pwm.cli demo    # load the synthetic fixture for the local user and process it
uv run python -m pwm.cli work    # run any pending jobs
uv run python -m pwm.cli reset   # delete the local user and everything derived from them
"""

import argparse
import json
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from pwm.config import get_settings
from pwm.db.models import User
from pwm.db.session import get_engine
from pwm.extraction.factory import build_stages
from pwm.pipeline.store import ensure_user, ingest
from pwm.pipeline.worker import run_all
from pwm.sources import Party, SourceRecord

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "synthetic" / "sources.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["demo", "work", "reset"])
    command = parser.parse_args().command
    settings = get_settings()

    with Session(get_engine()) as session:
        if command == "reset":
            session.execute(delete(User).where(User.email == settings.dev_user_email))
            session.commit()
            print("local user and all derived data deleted")
            return
        if command == "demo":
            records = [SourceRecord.model_validate(r) for r in json.loads(FIXTURE.read_text())]
            user = ensure_user(
                session, Party(name=settings.dev_user_name, address=settings.dev_user_email)
            )
            print(f"ingested {ingest(session, user, records)} new sources")
            session.commit()
        triager, extractor = build_stages()
        print(f"ran {run_all(session, triager, extractor)} job(s) with {extractor.method}")


if __name__ == "__main__":
    main()
