"""Migrations are tested against a database that already holds data, because that is
where they break. Uses its own throwaway database."""

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from pwm.config import get_settings

ADMIN_URL = os.environ.get("PWM_TEST_ADMIN_URL", "postgresql+psycopg://pwm:pwm@localhost:5433/pwm")
URL = ADMIN_URL.rsplit("/", 1)[0] + "/pwm_migration_test"


@pytest.fixture
def alembic(monkeypatch: pytest.MonkeyPatch) -> Iterator[Config]:
    try:
        with create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT").connect() as admin:
            admin.execute(text("drop database if exists pwm_migration_test with (force)"))
            admin.execute(text("create database pwm_migration_test"))
    except OperationalError:
        pytest.skip("Postgres is not reachable: run `docker compose up -d --wait db`")
    monkeypatch.setenv("PWM_DATABASE_URL", URL)
    assert get_settings().database_url == URL
    config = Config("alembic.ini")
    config.attributes["configure_logger"] = False
    yield config


def test_upgrading_a_database_that_already_holds_corrections(alembic: Config) -> None:
    command.upgrade(alembic, "0002")
    user, source, original, fixed = uuid4(), uuid4(), uuid4(), uuid4()
    row = (
        "insert into assertions (id, user_id, source_id, kind, subject, predicate, value, evidence_quote,"
        " extraction_method, prompt_version, origin, review, confidence, observed_at, superseded_by_id)"
        " values (:id, :u, :s, 'commitment', 'Alex', 'committed_to', :v, 'I will send it.',"
        " :m, :pv, 'source_explicit', :r, 'high', now(), :sup)"
    )
    engine = create_engine(URL)
    with engine.begin() as db:
        db.execute(text("insert into users (id, email) values (:u, 'a@example.com')"), {"u": user})
        db.execute(
            text("insert into sources (id, user_id, external_id, kind, observed_at, record, suspicious)"
                 " values (:s, :u, 'm1', 'email', now(), '{}', false)"),
            {"s": source, "u": user},
        )  # fmt: skip
        db.execute(text(row), {"id": fixed, "u": user, "s": source, "v": "send the deck", "m": "user_correction",
                               "pv": f"of:{original}", "r": "confirmed", "sup": None})  # fmt: skip
        db.execute(text(row), {"id": original, "u": user, "s": source, "v": "send it", "m": "heuristic",
                               "pv": "heuristic-v1", "r": "corrected", "sup": fixed})  # fmt: skip
        db.execute(
            text("insert into assertion_relations (id, user_id, type, from_id, to_id)"
                 " values (:i, :u, 'supersedes', :f, :t)"),
            {"i": uuid4(), "u": user, "f": fixed, "t": original},
        )  # fmt: skip

    command.upgrade(alembic, "head")
    with engine.connect() as db:
        ordinals = dict(db.execute(text("select extraction_method, ordinal from assertions")).all())  # type: ignore[arg-type]
        assert ordinals == {"heuristic": 0, "user_correction": 1}
        assert db.execute(text("select made_by from assertion_relations")).scalar_one() == "user"
        assert (
            db.execute(text("select count(*) from sources where connector = 'manual'")).scalar_one()
            == 1
        )

    command.downgrade(alembic, "0002")
    command.upgrade(alembic, "head")
    engine.dispose()
