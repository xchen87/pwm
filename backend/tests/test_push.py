"""Phone delivery, against a stand-in for Expo's push service. Nothing here reaches a phone."""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm.brief import service
from pwm.brief.writer import TemplateBriefWriter
from pwm.db.models import Device, Notification, User
from pwm.push import ExpoPushNotifier

TOKEN = "ExponentPushToken[abcdefghijklmnopqrstuv]"
SINCE = "2026-08-29T00:00:00+00:00"


class StandInExpo:
    """Answers like Expo's push endpoint; remembers what it was sent."""

    def __init__(self, *tickets: dict[str, Any]) -> None:
        self.sent: list[Any] = []
        self._tickets = list(tickets)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request.read())
        import json

        messages = json.loads(request.content)
        tickets = self._tickets or [{"status": "ok", "id": f"t{n}"} for n, _ in enumerate(messages)]
        return httpx.Response(200, json={"data": tickets})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture(autouse=True)
def demo_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PWM_FIXED_NOW", "2026-09-12T09:00:00+00:00")


def test_a_registered_phone_is_told_a_brief_is_ready_and_nothing_else(
    client: TestClient, session: Session, world: User
) -> None:
    assert (
        client.post("/devices", json={"push_token": TOKEN, "platform": "android"}).status_code
        == 200
    )
    assert (
        client.post("/devices", json={"push_token": TOKEN, "platform": "android"}).status_code
        == 200
    )
    assert len(session.scalars(select(Device)).all()) == 1

    expo = StandInExpo()
    from datetime import datetime

    brief = service.generate(
        session,
        world,
        TemplateBriefWriter(),
        ExpoPushNotifier(expo.client(), "https://expo.test/send"),
        "weekly",
        datetime.fromisoformat(SINCE),
    )
    assert brief.items
    (payload,) = expo.sent
    text = payload.decode()
    assert (
        TOKEN in text and "Your World Brief is ready" in text and f"pwm://brief/{brief.id}" in text
    )
    for leaked in ("Alex", "Tom", "$", "Q3", "dentist", "Sokolova"):
        assert leaked.lower() not in text.lower(), leaked
    note = session.scalars(select(Notification)).one()
    assert note.channel == "push" and note.deep_link == f"pwm://brief/{brief.id}"
    assert client.get(f"/briefs/{brief.id}").json()["id"] == str(brief.id)


def test_a_dead_token_is_dropped_and_expo_being_down_loses_nothing(
    client: TestClient, session: Session, world: User
) -> None:
    from datetime import datetime

    client.post("/devices", json={"push_token": TOKEN, "platform": "ios"})
    dead = StandInExpo(
        {"status": "error", "message": "gone", "details": {"error": "DeviceNotRegistered"}}
    )
    service.generate(
        session,
        world,
        TemplateBriefWriter(),
        ExpoPushNotifier(dead.client(), "https://expo.test/send"),
        "weekly",
        datetime.fromisoformat(SINCE),
    )
    assert session.scalars(select(Device)).all() == []
    assert len(session.scalars(select(Notification)).all()) == 1

    client.post("/devices", json={"push_token": TOKEN, "platform": "ios"})
    down = httpx.Client(
        transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")))
    )
    client.post("/notifications/read")
    service.generate(
        session,
        world,
        TemplateBriefWriter(),
        ExpoPushNotifier(down, "https://expo.test/send"),
        "daily",
        datetime.fromisoformat(SINCE),
    )
    assert len(session.scalars(select(Notification)).all()) == 2  # the inbox row still arrived
    assert len(session.scalars(select(Device)).all()) == 1  # and the device was not blamed


def test_sign_out_unregisters_the_phone_and_bad_tokens_are_refused(client: TestClient) -> None:
    for bad in ("not-a-token", "ExponentPushToken[]", "ExponentPushToken[x]; drop", "x" * 300):
        assert (
            client.post("/devices", json={"push_token": bad, "platform": "ios"}).status_code == 422
        ), bad
    assert (
        client.post("/devices", json={"push_token": TOKEN, "platform": "windows"}).status_code
        == 422
    )
    client.post("/devices", json={"push_token": TOKEN, "platform": "ios"})
    assert (
        client.request(
            "DELETE", "/devices", json={"push_token": TOKEN, "platform": "ios"}
        ).status_code
        == 200
    )
    assert (
        client.request(
            "DELETE", "/devices", json={"push_token": TOKEN, "platform": "ios"}
        ).status_code
        == 404
    )


def test_a_brief_belongs_to_its_owner(client: TestClient, session: Session, world: User) -> None:
    from uuid import uuid4

    from pwm.db.models import Brief
    from pwm.pipeline.store import ensure_user
    from pwm.sources import Party

    client.post("/briefs?period=weekly")
    brief = session.scalars(select(Brief)).one()
    other = ensure_user(session, Party(name="Other", address="other@example.com"))
    stolen = Brief(
        user_id=other.id,
        period="daily",
        covers_since=brief.covers_since,
        writer_version="x",
        items=[],
        created_at=brief.created_at,
    )
    session.add(stolen)
    session.commit()
    assert client.get(f"/briefs/{brief.id}").status_code == 200
    assert client.get(f"/briefs/{stolen.id}").status_code == 404
    assert client.get(f"/briefs/{uuid4()}").status_code == 404
    assert client.get("/briefs/latest").json()["id"] == str(brief.id)


def test_app_link_files_appear_only_when_the_identities_are_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/.well-known/apple-app-site-association").status_code == 404
    assert client.get("/.well-known/assetlinks.json").status_code == 404
    monkeypatch.setenv("PWM_APPLE_APP_ID", "TEAMID.com.personalworldmodel.app")
    monkeypatch.setenv("PWM_ANDROID_PACKAGE", "com.personalworldmodel.app")
    monkeypatch.setenv("PWM_ANDROID_CERT_FINGERPRINTS", '["AA:BB"]')
    apple = client.get("/.well-known/apple-app-site-association")
    assert (
        apple.status_code == 200
        and apple.json()["applinks"]["details"][0]["appID"] == "TEAMID.com.personalworldmodel.app"
    )
    android = client.get("/.well-known/assetlinks.json").json()
    assert android[0]["target"]["sha256_cert_fingerprints"] == ["AA:BB"]


def test_a_phone_belongs_to_whoever_is_signed_in_on_it(
    client: TestClient, session: Session, world: User
) -> None:
    from pwm.pipeline.store import ensure_user
    from pwm.sources import Party

    client.post("/devices", json={"push_token": TOKEN, "platform": "ios"})
    other = ensure_user(session, Party(name="Other", address="other@example.com"))
    session.add(
        Device(
            user_id=other.id,
            push_token=TOKEN,
            platform="ios",
            registered_at=world.created_at,
            last_seen_at=world.created_at,
        )
    )
    session.commit()
    client.post(
        "/devices", json={"push_token": TOKEN, "platform": "ios"}
    )  # this account signs in on the same phone
    owners = session.scalars(select(Device.user_id).where(Device.push_token == TOKEN)).all()
    assert owners == [world.id]


def test_devices_per_user_are_bounded_and_pushes_are_chunked(
    client: TestClient, session: Session, world: User
) -> None:
    from datetime import datetime

    for n in range(8):
        client.post(
            "/devices", json={"push_token": f"ExponentPushToken[device{n:022d}]", "platform": "ios"}
        )
    assert len(session.scalars(select(Device)).all()) == 5

    for n in range(200):
        session.add(
            Device(
                user_id=world.id,
                push_token=f"ExponentPushToken[bulk{n:024d}]",
                platform="ios",
                registered_at=world.created_at,
                last_seen_at=world.created_at,
            )
        )
    session.commit()
    expo = StandInExpo()
    service.generate(
        session,
        world,
        TemplateBriefWriter(),
        ExpoPushNotifier(expo.client(), "https://expo.test/send"),
        "weekly",
        datetime.fromisoformat(SINCE),
    )
    import json

    assert len(expo.sent) == 3 and all(len(json.loads(p)) <= 100 for p in expo.sent)
    assert all('"channelId":"default"' in p.decode().replace(" ", "") for p in expo.sent)


def test_expo_answering_nonsense_does_not_lose_the_brief(
    client: TestClient, session: Session, world: User
) -> None:
    from datetime import datetime

    client.post("/devices", json={"push_token": TOKEN, "platform": "ios"})
    html = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>gateway</html>"))
    )
    brief = service.generate(
        session,
        world,
        TemplateBriefWriter(),
        ExpoPushNotifier(html, "https://expo.test/send"),
        "weekly",
        datetime.fromisoformat(SINCE),
    )
    assert brief.items and len(session.scalars(select(Notification)).all()) == 1
