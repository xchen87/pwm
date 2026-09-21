from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pwm.db.models import User
from pwm.pipeline.store import ensure_user
from pwm.sources import Party


def q3(client: TestClient) -> dict:
    items = client.get("/commitments").json()
    return next(i for i in items if "Q3 numbers by Friday" in i["evidence_quote"])


def test_needs_attention_lists_unreviewed_commitments_as_possibilities(client: TestClient) -> None:
    items = client.get("/commitments").json()
    assert len(items) >= 10
    item = q3(client)
    assert (item["review"], item["origin"], item["direction"]) == (
        "unreviewed",
        "source_explicit",
        "by_user",
    )
    assert item["due"] == "2026-09-11" and item["overdue"] is True
    dues = [i["due"] for i in items if i["due"]]
    assert dues == sorted(dues)


def test_source_inspection_shows_the_quote_in_context(client: TestClient) -> None:
    detail = client.get(f"/assertions/{q3(client)['id']}").json()
    assert detail["context_quote"] == detail["evidence_quote"]
    assert "Finance only closed the books" in detail["context_before"]
    assert detail["source"]["sender_address"] == "alex.rivera@example.com"
    assert detail["extraction_method"] == "heuristic"


def test_confirm_then_track_status(client: TestClient) -> None:
    item = q3(client)
    blocked = client.post(f"/assertions/{item['id']}/status", json={"status": "done"})
    assert blocked.status_code == 409

    assert client.post(f"/assertions/{item['id']}/confirm").json()["review"] == "confirmed"
    done = client.post(f"/assertions/{item['id']}/status", json={"status": "done"}).json()
    assert done["status"] == "done"
    assert item["id"] not in [i["id"] for i in client.get("/commitments").json()]


def test_dismissed_items_leave_the_list(client: TestClient) -> None:
    item = q3(client)
    assert client.post(f"/assertions/{item['id']}/dismiss").json()["review"] == "rejected"
    assert item["id"] not in [i["id"] for i in client.get("/commitments").json()]


def test_edit_replaces_the_item_with_the_users_version(client: TestClient) -> None:
    item = q3(client)
    fixed = client.post(
        f"/assertions/{item['id']}/correct",
        json={"what": "Send Tom the Q3 numbers", "due": "2026-09-25"},
    ).json()
    assert (fixed["origin"], fixed["review"], fixed["due"]) == (
        "user_stated",
        "confirmed",
        "2026-09-25",
    )
    assert fixed["related"][0]["relation"] == "supersedes"
    ids = [i["id"] for i in client.get("/commitments").json()]
    assert fixed["id"] in ids and item["id"] not in ids
    assert client.post(f"/assertions/{item['id']}/confirm").status_code == 409


def test_another_users_data_is_invisible(client: TestClient, session: Session, world: User) -> None:
    item = q3(client)
    ensure_user(session, Party(name="Other", address="other@example.com"))
    session.commit()
    from sqlalchemy import select

    from pwm.api.deps import current_user
    from pwm.api.main import app

    app.dependency_overrides[current_user] = lambda: session.scalar(
        select(User).where(User.email == "other@example.com")
    )
    assert client.get("/commitments").json() == []
    assert client.get(f"/assertions/{item['id']}").status_code == 404
    assert client.post(f"/assertions/{item['id']}/confirm").status_code == 404
    assert client.get(f"/assertions/{uuid4()}").status_code == 404


def test_bad_corrections_are_rejected_not_crashed_on(client: TestClient) -> None:
    item = q3(client)
    for body in ({"what": ""}, {"what": "   "}, {"what": "a\u0000b"}, {"committed_by": "x" * 300}):
        assert client.post(f"/assertions/{item['id']}/correct", json=body).status_code == 422, body
    assert q3(client)["review"] == "unreviewed"


def test_a_conflict_is_settled_by_dismissing_one_side(client: TestClient, session: Session) -> None:
    from pwm.db.models import Assertion, AssertionRelation

    a, b = client.get("/commitments").json()[:2]
    owner = session.get_one(Assertion, a["id"]).user_id
    session.add(
        AssertionRelation(
            user_id=owner, type="contradicts", from_id=a["id"], to_id=b["id"], made_by="user"
        )
    )
    session.commit()
    assert client.get(f"/assertions/{a['id']}").json()["has_conflict"] is True
    client.post(f"/assertions/{b['id']}/dismiss")
    detail = client.get(f"/assertions/{a['id']}").json()
    assert detail["has_conflict"] is False and detail["related"] == []


def test_dismissing_over_the_api_rereads_the_mailbox(client: TestClient, session: Session) -> None:
    from sqlalchemy import select

    from pwm.db.models import Assertion

    new = session.scalars(select(Assertion).where(Assertion.value == "19950")).one()
    old = session.scalars(select(Assertion).where(Assertion.value == "18400")).one()
    assert old.superseded_by_id == new.id
    assert client.post(f"/assertions/{new.id}/dismiss").status_code == 200
    session.refresh(old)
    assert old.superseded_by_id is None
    answer = client.post("/ask", json={"question": "What is the kitchen quote?"}).json()
    assert "18400" in answer["text"] and "19950" not in answer["text"]
