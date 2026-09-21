from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm import review
from pwm.brief import service
from pwm.brief.items import ItemKind, select_items
from pwm.brief.writer import TemplateBriefWriter
from pwm.config import get_settings
from pwm.db.models import Assertion, Notification, ProductEvent, User

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
SINCE = datetime(2026, 8, 29, tzinfo=UTC)


@pytest.fixture(autouse=True)
def demo_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PWM_FIXED_NOW", NOW.isoformat())
    get_settings.cache_clear() if hasattr(get_settings, "cache_clear") else None


def kinds(items: list) -> set[ItemKind]:
    return {i.kind for i in items}


def test_changes_conflicts_and_consumer_issues_are_found(session: Session, world: User) -> None:
    items = select_items(session, world, SINCE, NOW)
    assert {ItemKind.CHANGED, ItemKind.POSSIBLE_COMMITMENT, ItemKind.CONSUMER} <= kinds(items)
    changed = next(i for i in items if i.kind is ItemKind.CHANGED and i.predicate == "quote")
    assert (changed.previous_value, changed.value) == ("18400", "19950")
    assert changed.other_evidence_quote and "18,400" in changed.other_evidence_quote
    assert any(i.kind is ItemKind.CONSUMER and i.predicate == "monthly_price" for i in items)


def test_every_item_points_at_a_real_assertion_and_none_repeats(
    session: Session, world: User
) -> None:
    items = select_items(session, world, SINCE, NOW)
    ids = [i.assertion_id for i in items]
    assert len(ids) == len(set(ids)) <= 12
    assert all(session.get(Assertion, i) is not None for i in ids)


def test_unconfirmed_items_are_never_worded_as_fact(session: Session, world: User) -> None:
    written = TemplateBriefWriter().write(select_items(session, world, SINCE, NOW))
    for w in written:
        if not w.item.is_fact:
            assert w.headline.startswith(("Possible", "It looks like", "Two sources disagree")), (
                w.headline
            )


def test_confirmed_commitments_due_soon_lead_the_brief(session: Session, world: User) -> None:
    tax = session.scalars(
        select(Assertion).where(Assertion.evidence_quote.contains("estimated tax payment"))
    ).one()
    review.confirm(session, world, tax.id)
    items = select_items(session, world, SINCE, NOW)
    assert items[0].kind is ItemKind.DUE_SOON and items[0].assertion_id == tax.id


def test_dismissed_items_and_low_confidence_guesses_stay_out(session: Session, world: User) -> None:
    items = select_items(session, world, SINCE, NOW)
    target = next(i for i in items if i.kind is ItemKind.POSSIBLE_COMMITMENT)
    review.dismiss(session, world, target.assertion_id)
    after = select_items(session, world, SINCE, NOW)
    assert target.assertion_id not in [i.assertion_id for i in after]
    assert all(i.is_fact or i.confidence != "low" for i in after)


def test_the_notification_carries_no_personal_content(session: Session, world: User) -> None:
    brief = service.generate(
        session, world, TemplateBriefWriter(), service.InboxNotifier(), "weekly", SINCE
    )
    assert brief.items
    note = session.scalars(select(Notification)).one()
    assert note.title == "Your World Brief is ready"
    assert note.deep_link == f"pwm://brief/{brief.id}"
    for leaked in ("Alex", "Tom", "$", "Q3", "dentist"):
        assert leaked.lower() not in note.title.lower()


def test_an_empty_brief_sends_no_notification(session: Session, user: User) -> None:
    service.generate(session, user, TemplateBriefWriter(), service.InboxNotifier())
    assert session.scalars(select(Notification)).all() == []


def test_home_brief_notifications_and_events_over_the_api(
    client: TestClient, session: Session
) -> None:
    home = client.get("/home").json()
    assert home["what_changed"] and home["needs_attention_total"] >= 10
    assert len(home["needs_attention"]) == 3
    assert any("sister" in r["evidence_quote"] for r in home["remembered"])

    brief = client.post("/briefs?period=weekly").json()
    assert brief["items"] and client.get("/briefs/latest").json()["id"] == brief["id"]
    assert client.get("/home").json()["unread_notifications"] == 1
    client.post("/notifications/read")
    assert client.get("/home").json()["unread_notifications"] == 0

    assert (
        client.post("/events", json={"name": "brief_opened", "subject_id": brief["id"]}).status_code
        == 200
    )
    assert client.post("/events", json={"name": "made_up"}).status_code == 422
    assert session.scalars(select(ProductEvent.name)).all() == ["brief_opened"]
    assert client.post("/briefs?period=hourly").status_code == 422


def test_what_changed_is_measured_from_the_previous_visit(
    client: TestClient, session: Session, world: User
) -> None:
    client.post("/visits")
    client.post("/visits")  # same visit: must not wipe what changed
    assert client.get("/home").json()["what_changed"]
    world.previous_seen_at = NOW  # a later visit, after everything was seen
    session.commit()
    assert client.get("/home").json()["what_changed"] == [
        w
        for w in client.get("/home").json()["what_changed"]
        if w["item"]["kind"] in ("consumer", "remembered")
    ]


def test_dates_and_money_read_the_way_a_person_writes_them() -> None:
    from pwm.brief.writer import readable

    assert readable("date", "2026-09-27T18:00") == "Sun, Sep 27 at 6:00 PM"
    assert readable("date", "2026-09-26") == "Sat, Sep 26"
    assert readable("quote", "19950") == "$19,950"
    assert readable("monthly_price", "18.99") == "$18.99"
    assert readable("phone", "555-0142") == "555-0142"
    assert readable("quote", "about twenty grand") == "about twenty grand"
