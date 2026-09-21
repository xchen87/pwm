"""Slice 4 against the fake Google: sign-in, encrypted tokens, sync, failures, revocation.

Everything here proves our side of Google's documented contract. None of it has run
against Google itself.
"""

import base64
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pwm import crypto
from pwm.api.auth import google_client
from pwm.api.main import app
from pwm.config import get_settings
from pwm.connectors import service
from pwm.db.models import (
    Assertion,
    AuthSession,
    Connection,
    Job,
    LoginCode,
    OAuthState,
    OAuthToken,
    Source,
    User,
)
from pwm.db.session import get_session
from pwm.devtools.fake_google import app as fake_app
from pwm.devtools.fake_google import fake
from pwm.google.http import GoogleClient, GoogleError
from pwm.pipeline.heuristic import HeuristicExtractor, HeuristicTriager
from pwm.pipeline.worker import run_all
from pwm.sources import Party, SourceKind, SourceRecord

G = "http://testserver"
STAGES = (HeuristicTriager(), HeuristicExtractor())


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "PWM_GOOGLE_CLIENT_ID": "client-id", "PWM_GOOGLE_CLIENT_SECRET": "client-secret",
        "PWM_DATA_KEY": base64.b64encode(os.urandom(32)).decode(),
        "PWM_GOOGLE_AUTH_URL": f"{G}/o/oauth2/v2/auth", "PWM_GOOGLE_TOKEN_URL": f"{G}/token",
        "PWM_GOOGLE_REVOKE_URL": f"{G}/revoke", "PWM_GOOGLE_USERINFO_URL": f"{G}/v1/userinfo",
        "PWM_GOOGLE_API_URL": G, "PWM_FIXED_NOW": "2026-09-12T09:00:00+00:00",
    }  # fmt: skip
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    fake.reset()


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch) -> GoogleClient:
    waits: list[float] = []
    client = GoogleClient(get_settings(), http=TestClient(fake_app), sleep=waits.append)
    client.waits = waits  # type: ignore[attr-defined]
    monkeypatch.setattr(service, "google_client", lambda: client)
    return client


@pytest.fixture
def api(session: Session, google: GoogleClient) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[google_client] = lambda: google
    yield TestClient(app)
    app.dependency_overrides.clear()


def sign_in(api: TestClient, redirect: str = "pwm://auth") -> str:
    """Walk the browser through the whole flow; returns a session token."""
    started = api.get("/auth/google/start", params={"redirect": redirect}, follow_redirects=False)
    assert started.status_code == 302
    consent = TestClient(fake_app).get(started.headers["location"], follow_redirects=False)
    back = urlparse(consent.headers["location"])
    returned = api.get(f"{back.path}?{back.query}", follow_redirects=False)
    assert returned.status_code == 302, returned.text
    target = urlparse(returned.headers["location"])
    assert returned.headers["location"].startswith(redirect)
    code = parse_qs(target.query)["code"][0]
    granted = api.post("/auth/session", json={"code": code})
    assert granted.status_code == 200
    return str(granted.json()["token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


# ---------------------------------------------------------------- sign-in


def test_sign_in_creates_a_user_a_session_and_an_encrypted_token(
    api: TestClient, session: Session
) -> None:
    token = sign_in(api)
    me = api.get("/auth/me", headers=bearer(token)).json()
    assert me == {
        "email": "alex.rivera@example.com",
        "name": "Alex Rivera",
        "signed_in_with_google": True,
    }

    stored = session.scalars(select(OAuthToken)).one()
    assert stored.refresh_token_encrypted.startswith("enc:v1:")
    assert crypto.decrypt(stored.refresh_token_encrypted, "google-refresh") in fake.refresh_tokens
    assert token not in str(session.scalars(select(AuthSession.token_hash)).all())
    assert count(session, OAuthState) == 0 and count(session, LoginCode) == 0
    assert {c.connector for c in session.scalars(select(Connection))} == {
        "gmail",
        "google_calendar",
    }
    assert sorted(j.key for j in session.scalars(select(Job))) == ["gmail", "google_calendar"]


def test_the_session_token_never_appears_in_a_url(api: TestClient) -> None:
    started = api.get(
        "/auth/google/start", params={"redirect": "pwm://auth"}, follow_redirects=False
    )
    assert (
        "code_challenge=" in started.headers["location"] and "S256" in started.headers["location"]
    )
    assert "client_secret" not in started.headers["location"]
    token = sign_in(api)
    assert len(token) > 40


def test_redirects_are_allow_listed(api: TestClient) -> None:
    for target in ("https://evil.example/steal", "javascript:alert(1)", "pwm.evil://auth"):
        assert (
            api.get(
                "/auth/google/start", params={"redirect": target}, follow_redirects=False
            ).status_code
            == 400
        )


def test_a_login_code_works_once_and_a_state_works_once(api: TestClient, session: Session) -> None:
    started = api.get(
        "/auth/google/start", params={"redirect": "pwm://auth"}, follow_redirects=False
    )
    consent = TestClient(fake_app).get(started.headers["location"], follow_redirects=False)
    back = urlparse(consent.headers["location"])
    first = api.get(f"{back.path}?{back.query}", follow_redirects=False)
    assert (
        api.get(f"{back.path}?{back.query}", follow_redirects=False).status_code == 400
    )  # replayed callback
    code = parse_qs(urlparse(first.headers["location"]).query)["code"][0]
    assert api.post("/auth/session", json={"code": code}).status_code == 200
    assert api.post("/auth/session", json={"code": code}).status_code == 400
    assert (
        api.get("/auth/google/callback?state=made-up&code=x", follow_redirects=False).status_code
        == 400
    )


def test_refusing_mail_access_is_not_a_sign_in(api: TestClient, session: Session) -> None:
    fake.granted_scopes = "openid email profile"
    started = api.get(
        "/auth/google/start", params={"redirect": "pwm://auth"}, follow_redirects=False
    )
    consent = TestClient(fake_app).get(started.headers["location"], follow_redirects=False)
    back = urlparse(consent.headers["location"])
    assert api.get(f"{back.path}?{back.query}", follow_redirects=False).status_code == 400
    assert count(session, User) == 0 and count(session, OAuthToken) == 0


def test_sessions_scope_data_and_end_on_sign_out(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = sign_in(api)
    assert api.get("/home", headers=bearer(token)).status_code == 200
    assert api.get("/home", headers=bearer("not-a-token")).status_code == 401
    monkeypatch.setenv("PWM_ENVIRONMENT", "production")
    assert api.get("/home").status_code == 401  # no dev user outside local
    assert api.get("/home", headers=bearer(token)).status_code == 200  # a real session works
    api.post("/auth/logout", headers=bearer(token))
    assert api.get("/home", headers=bearer(token)).status_code == 401


def test_without_configuration_google_is_simply_unavailable(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PWM_DATA_KEY")
    assert (
        api.get(
            "/auth/google/start", params={"redirect": "pwm://auth"}, follow_redirects=False
        ).status_code
        == 400
    )
    available = {
        a["connector"]: a["available"] for a in api.get("/connections").json()["available"]
    }
    assert available["gmail"] is False


# ---------------------------------------------------------------- sync


def signed_in_user(api: TestClient, session: Session) -> User:
    sign_in(api)
    return session.scalars(select(User).where(User.google_sub.is_not(None))).one()


def test_first_sync_is_newest_first_in_pages_and_builds_the_world(
    api: TestClient, session: Session
) -> None:
    user = signed_in_user(api, session)
    gmail = service.build_connector(session, user, "gmail")
    first = gmail.fetch(None)
    assert first.more and len(first.records) == 50
    assert first.records[0].observed_at == max(r.observed_at for r in first.records)
    assert json.loads(first.cursor or "{}")["mode"] == "backfill"

    jobs = run_all(session, *STAGES)
    assert jobs >= 4  # gmail pages + calendar, each queued by the one before
    assert (
        count(session, Source) == 104 + 15
    )  # every mail and every calendar entry; notes are not Google data
    statuses = {c.connector: c.status for c in session.scalars(select(Connection))}
    assert statuses == {"gmail": "ok", "google_calendar": "ok"}
    quotes = session.scalars(select(Assertion.evidence_quote)).all()
    assert any("Q3 numbers by Friday" in q for q in quotes)


def test_message_bodies_are_encrypted_at_rest(api: TestClient, session: Session) -> None:
    signed_in_user(api, session)
    run_all(session, *STAGES)
    stored = session.scalars(select(Source).where(Source.external_id == "gmail:e_q3_1")).one()
    assert stored.record["body"].startswith("enc:v1:") and "Q3" not in json.dumps(
        stored.record["body"]
    )
    assert stored.record["subject"] == "Q3 numbers"  # metadata stays queryable


def test_incremental_sync_brings_only_new_mail_and_syncing_twice_changes_nothing(
    api: TestClient, session: Session
) -> None:
    user = signed_in_user(api, session)
    run_all(session, *STAGES)
    before = count(session, Source)
    gmail = service.build_connector(session, user, "gmail")
    assert service.sync(session, user, gmail, *STAGES) == 0

    fake.deliver(
        SourceRecord(
            id="new1", kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, 12, 8, tzinfo=UTC), thread_id="tn",
            sender=Party(name="Tom Okafor", address="tom.okafor@brightwave.example"),
            recipients=(Party(name="Alex Rivera", address="alex.rivera@example.com"),),
            subject="One more thing", body="I'll send the budget sheet by Tuesday.", provider_labels=("INBOX",),
        )
    )  # fmt: skip
    assert service.sync(session, user, gmail, *STAGES) == 1
    assert count(session, Source) == before + 1
    assert session.scalars(
        select(Assertion).where(Assertion.evidence_quote.contains("budget sheet"))
    ).one()


def test_a_moved_calendar_event_is_reported_as_a_change(api: TestClient, session: Session) -> None:
    user = signed_in_user(api, session)
    run_all(session, *STAGES)
    fake.reschedule(
        "c_walkthrough", datetime(2026, 9, 25, 8, 30, tzinfo=UTC), datetime(2026, 9, 25, 9, 30, tzinfo=UTC),
        datetime(2026, 9, 11, 17, tzinfo=UTC),
    )  # fmt: skip
    calendar = service.build_connector(session, user, "google_calendar")
    assert service.sync(session, user, calendar, *STAGES) == 1
    old = session.scalars(select(Assertion).where(Assertion.value == "2026-09-24T08:30")).one()
    new = session.scalars(select(Assertion).where(Assertion.value == "2026-09-25T08:30")).one()
    assert old.superseded_by_id == new.id


# ---------------------------------------------------------------- failures


def test_rate_limits_and_server_errors_are_retried_with_backoff(
    api: TestClient, session: Session, google: GoogleClient
) -> None:
    user = signed_in_user(api, session)
    fake.fail_next, fake.retry_after = [429, 503], "7"
    gmail = service.build_connector(session, user, "gmail")
    assert len(gmail.fetch(None).records) == 50
    assert google.waits[:2] == [7.0, 7.0]  # type: ignore[attr-defined]


def test_retries_are_bounded(api: TestClient, session: Session, google: GoogleClient) -> None:
    user = signed_in_user(api, session)
    fake.fail_next = [500] * 10
    with pytest.raises(GoogleError) as failure:
        service.build_connector(session, user, "gmail").fetch(None)
    assert failure.value.status == 500 and "injected" not in str(failure.value)


def test_an_expired_access_token_is_refreshed_mid_sync(api: TestClient, session: Session) -> None:
    user = signed_in_user(api, session)
    gmail = service.build_connector(session, user, "gmail")
    gmail.fetch(None)
    fake.expire_access_tokens()
    assert gmail.fetch(None).records


def test_forgotten_history_and_expired_sync_tokens_fall_back_to_a_full_read(
    api: TestClient, session: Session
) -> None:
    user = signed_in_user(api, session)
    run_all(session, *STAGES)
    before = count(session, Source)
    fake.forget_history, fake.expire_sync_tokens = True, True
    for name in ("gmail", "google_calendar"):
        service.sync(session, user, service.build_connector(session, user, name), *STAGES)
    run_all(session, *STAGES)
    assert count(session, Source) == before  # re-read, nothing duplicated


def test_a_revoked_grant_asks_for_reconnection_instead_of_retrying_forever(
    api: TestClient, session: Session
) -> None:
    user = signed_in_user(api, session)
    fake.revoke_everything()
    run_all(session, *STAGES)
    gmail = session.scalars(select(Connection).where(Connection.connector == "gmail")).one()
    assert (gmail.status, gmail.last_error) == ("needs_reconnect", "GrantRevoked")
    assert all(j.status == "done" for j in session.scalars(select(Job)))
    assert user.email == "alex.rivera@example.com"


# ---------------------------------------------------------------- taking it back


def test_disconnecting_the_last_google_source_revokes_and_destroys_the_token(
    api: TestClient, session: Session
) -> None:
    token = sign_in(api)
    run_all(session, *STAGES)
    refresh = crypto.decrypt(
        session.scalars(select(OAuthToken)).one().refresh_token_encrypted, "google-refresh"
    )

    api.delete("/connections/gmail", headers=bearer(token))
    assert count(session, OAuthToken) == 1 and fake.revoked == []  # calendar still uses the grant
    assert count(session, Source) == 15

    api.delete("/connections/google_calendar", headers=bearer(token))
    assert count(session, OAuthToken) == 0 and fake.revoked == [refresh]
    assert count(session, Source) == 0 and count(session, Assertion) == 0


def test_delete_everything_revokes_at_google_too(api: TestClient, session: Session) -> None:
    token = sign_in(api)
    run_all(session, *STAGES)
    assert api.delete("/me", headers=bearer(token)).status_code == 200
    assert len(fake.revoked) == 1
    for model in (User, Source, Assertion, OAuthToken, AuthSession, Connection):
        assert count(session, model) == 0, model.__tablename__
    assert api.get("/home", headers=bearer(token)).status_code == 401


def test_a_verified_google_email_adopts_an_unlinked_account_but_never_a_linked_one(
    api: TestClient, session: Session
) -> None:
    api.get("/connections")  # creates the local development user: same email, no Google link
    dev = session.scalars(select(User)).one()
    assert dev.google_sub is None
    sign_in(api)
    session.refresh(dev)
    assert count(session, User) == 1 and dev.google_sub == "fake-sub-1001"

    dev.google_sub = "someone-else"  # the address now belongs to another Google identity here
    session.commit()
    started = api.get(
        "/auth/google/start", params={"redirect": "pwm://auth"}, follow_redirects=False
    )
    consent = TestClient(fake_app).get(started.headers["location"], follow_redirects=False)
    back = urlparse(consent.headers["location"])
    assert api.get(f"{back.path}?{back.query}", follow_redirects=False).status_code == 400
