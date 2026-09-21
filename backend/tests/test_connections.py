from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pwm.api.main import app
from pwm.db.models import Assertion, Brief, Person, Source, User
from pwm.db.session import get_session


def fresh_client(session: Session) -> TestClient:
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_onboarding_from_nothing_to_a_first_brief(session: Session) -> None:
    client = fresh_client(session)
    try:
        start = client.get("/connections").json()
        assert start["connected"] == [] and start["understood"] == 0
        assert {a["connector"]: a["available"] for a in start["available"]} == {
            "gmail": False, "google_calendar": False, "demo": True,
        }  # fmt: skip
        assert client.get("/home").json()["needs_attention_total"] == 0

        result = client.post("/connections/demo").json()
        assert result["new_sources"] == 122 and result["understood"] > 30
        assert client.post("/connections/demo").json()["new_sources"] == 0
        assert count(session, Source) == 122 and count(session, Brief) == 1

        connected = client.get("/connections").json()["connected"]
        assert [(c["connector"], c["sources"]) for c in connected] == [("demo", 122)]
        assert client.get("/home").json()["needs_attention_total"] >= 10
        assert client.get("/briefs/latest").json()["items"]
    finally:
        app.dependency_overrides.clear()


def test_disconnecting_removes_what_the_connection_brought_but_keeps_the_users_notes(
    session: Session,
) -> None:
    client = fresh_client(session)
    try:
        client.post("/connections/demo")
        client.post("/memories", json={"text": "The spare key is with Marguerite next door."})
        removed = client.delete("/connections/demo").json()
        assert removed["removed_sources"] == 122
        assert client.get("/commitments").json() == []
        assert count(session, Person) == 0
        kinds = session.scalars(select(Assertion.kind)).all()
        assert kinds == ["memory"]
        assert client.delete("/connections/demo").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_delete_everything_leaves_no_trace(session: Session) -> None:
    client = fresh_client(session)
    try:
        client.post("/connections/demo")
        assert client.delete("/me").status_code == 200
        assert count(session, Source) == count(session, Assertion) == count(session, Brief) == 0
        assert count(session, User) == 1  # the empty local identity, ready for onboarding again
        assert client.get("/connections").json()["connected"] == []
    finally:
        app.dependency_overrides.clear()
