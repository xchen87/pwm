"""Database-backed tests run against a throwaway `pwm_test` database on the local Postgres
(`docker compose up -d db`). They are skipped, loudly, when it is not reachable."""

import os

# The server fails closed: "local" (dev user, demo mailbox, Expo Go redirects) is opt-in.
os.environ.setdefault("PWM_ENVIRONMENT", "local")
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from pwm.api.main import app
from pwm.db.models import Base, User
from pwm.db.session import get_session
from pwm.pipeline.heuristic import HeuristicExtractor, HeuristicTriager
from pwm.pipeline.store import ensure_user, ingest, process_user
from pwm_eval.fixture import load_fixture

ADMIN_URL = os.environ.get("PWM_TEST_ADMIN_URL", "postgresql+psycopg://pwm:pwm@localhost:5433/pwm")
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/pwm_test"
FIXTURE = load_fixture()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    try:
        with create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT").connect() as admin:
            if not admin.scalar(text("select 1 from pg_database where datname = 'pwm_test'")):
                admin.execute(text("create database pwm_test"))
    except OperationalError:
        pytest.skip("Postgres is not reachable: run `docker compose up -d --wait db`")
    test_engine = create_engine(TEST_URL)
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as db:
        yield db
        db.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


@pytest.fixture
def user(session: Session) -> User:
    return ensure_user(session, FIXTURE.gold.user)


@pytest.fixture
def world(session: Session, user: User) -> User:
    """The synthetic fixture, ingested and processed with the rule-based stages."""
    ingest(session, user, FIXTURE.sources)
    process_user(session, user, HeuristicTriager(), HeuristicExtractor())
    session.commit()
    return user


@pytest.fixture
def client(session: Session, world: User) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
