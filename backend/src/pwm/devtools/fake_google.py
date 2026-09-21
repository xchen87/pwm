"""A stand-in for Google, for tests and local development only.

It serves the synthetic mailbox through the documented shapes of the OAuth 2.0, OpenID
userinfo, Gmail v1 and Calendar v3 endpoints this project uses, and can be told to
misbehave (rate limits, server errors, expired access tokens, forgotten history ids,
expired sync tokens, a revoked grant). It proves our side of the contract as we read the
documentation. It cannot prove Google agrees: only a real OAuth client can.

Run it:  uv run uvicorn pwm.devtools.fake_google:app --port 9090
"""

import base64
import hashlib
import secrets
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from pwm.connectors.demo import fixture_records
from pwm.sources import SourceKind, SourceRecord

ACCOUNT = {"sub": "fake-sub-1001", "email": "alex.rivera@example.com", "name": "Alex Rivera"}
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def gmail_json(record: SourceRecord, history_id: int) -> dict[str, Any]:
    sender = record.sender
    headers = [
        {"name": "From", "value": f"{sender.name or ''} <{sender.address}>" if sender else ""},
        {
            "name": "To",
            "value": ", ".join(f"{p.name or ''} <{p.address}>" for p in record.recipients),
        },
        {"name": "Subject", "value": record.subject},
        *({"name": name, "value": value} for name, value in record.headers.items()),
    ]
    return {
        "id": record.id,
        "threadId": record.thread_id or record.id,
        "historyId": str(history_id),
        "internalDate": str(int(record.observed_at.timestamp() * 1000)),
        "labelIds": list(record.provider_labels),
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": headers,
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64(record.body)}},
                {"mimeType": "text/html", "body": {"data": _b64(f"<p>{record.subject}</p>")}},
            ],
        },
    }


def event_json(record: SourceRecord) -> dict[str, Any]:
    assert record.starts_at and record.ends_at
    return {
        "id": record.id,
        "status": record.event_status or "confirmed",
        "summary": record.subject,
        "description": record.body,
        "location": record.location,
        "updated": record.observed_at.isoformat().replace("+00:00", "Z"),
        "start": {"dateTime": record.starts_at.isoformat()},
        "end": {"dateTime": record.ends_at.isoformat()},
        "attendees": [{"email": ACCOUNT["email"], "self": True}]
        + [{"email": p.address, "displayName": p.name} for p in record.recipients],
    }


class FakeGoogle:
    """All the state, so a test can inspect it and make it misbehave."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        records = sorted(fixture_records(), key=lambda r: r.observed_at)
        mail = [r for r in records if r.kind is SourceKind.EMAIL]
        self.messages = {r.id: gmail_json(r, 1000 + n) for n, r in enumerate(mail)}
        self.events = {r.id: event_json(r) for r in records if r.kind is SourceKind.CALENDAR_EVENT}
        self.history_id = 1000 + len(mail)
        self.added: list[tuple[int, str]] = []  # (history id, message id) since start
        self.sync_generation = 1
        self.codes: dict[str, dict[str, str]] = {}
        self.refresh_tokens: set[str] = set()
        self.access_tokens: set[str] = set()
        self.revoked: list[str] = []
        self.fail_next: list[int] = []  # status codes to return for the next API calls
        self.retry_after: str | None = None
        self.forget_history = False
        self.expire_sync_tokens = False
        self.granted_scopes = f"openid email profile {GMAIL_SCOPE} {CALENDAR_SCOPE}"
        self.calls: list[str] = []

    def deliver(self, record: SourceRecord) -> None:
        """New mail arrives."""
        self.history_id += 1
        self.messages[record.id] = gmail_json(record, self.history_id)
        self.added.append((self.history_id, record.id))

    def reschedule(self, event_id: str, start: datetime, end: datetime, updated: datetime) -> None:
        event = self.events[event_id]
        event["start"], event["end"] = (
            {"dateTime": start.isoformat()},
            {"dateTime": end.isoformat()},
        )
        event["updated"] = updated.isoformat().replace("+00:00", "Z")
        self.sync_generation += 1
        event["_changed_in"] = self.sync_generation

    def expire_access_tokens(self) -> None:
        self.access_tokens.clear()

    def revoke_everything(self) -> None:
        self.refresh_tokens.clear()
        self.access_tokens.clear()


fake = FakeGoogle()
app = FastAPI(title="Fake Google (tests and local development only)")


def _authorised(authorization: str | None, path: str) -> None:
    fake.calls.append(path)
    if fake.fail_next:
        status = fake.fail_next.pop(0)
        headers = {"Retry-After": fake.retry_after} if fake.retry_after else None
        raise HTTPException(status, "injected failure", headers=headers)
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token not in fake.access_tokens:
        raise HTTPException(401, "invalid credentials")


@app.get("/o/oauth2/v2/auth")
def authorize(
    client_id: str, redirect_uri: str, state: str, code_challenge: str,
    code_challenge_method: str = "S256", response_type: str = "code", access_type: str = "",
) -> RedirectResponse:  # fmt: skip
    if response_type != "code" or code_challenge_method != "S256" or access_type != "offline":
        raise HTTPException(400, "unsupported request")
    code = secrets.token_urlsafe(16)
    fake.codes[code] = {"challenge": code_challenge, "redirect_uri": redirect_uri}
    return RedirectResponse(f"{redirect_uri}?{urlencode({'code': code, 'state': state})}", 302)


async def _form(request: Request) -> dict[str, str]:
    # Parsed by hand so the fake needs no form-parsing dependency.
    fields = parse_qs((await request.body()).decode(), keep_blank_values=True)
    return {name: values[0] for name, values in fields.items()}


@app.post("/token")
async def token(request: Request) -> JSONResponse:
    form = await _form(request)
    if not form.get("client_id") or not form.get("client_secret"):
        return JSONResponse({"error": "invalid_client"}, 401)
    grant_type = form.get("grant_type")
    if grant_type == "authorization_code":
        issued = fake.codes.pop(form.get("code", ""), None)  # single use
        digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        if (
            not issued
            or issued["challenge"] != challenge
            or issued["redirect_uri"] != form.get("redirect_uri")
        ):
            return JSONResponse({"error": "invalid_grant"}, 400)
        refresh = "1//" + secrets.token_urlsafe(24)
        fake.refresh_tokens.add(refresh)
    elif grant_type == "refresh_token":
        if form.get("refresh_token") not in fake.refresh_tokens:
            return JSONResponse({"error": "invalid_grant"}, 400)
        refresh = ""
    else:
        return JSONResponse({"error": "unsupported_grant_type"}, 400)
    access = "ya29." + secrets.token_urlsafe(24)
    fake.access_tokens.add(access)
    body = {
        "access_token": access,
        "expires_in": 3599,
        "token_type": "Bearer",
        "scope": fake.granted_scopes,
    }
    return JSONResponse({**body, "refresh_token": refresh} if refresh else body)


@app.post("/revoke")
async def revoke(request: Request) -> dict[str, str]:
    revoked = (await _form(request)).get("token", "")
    fake.revoked.append(revoked)
    fake.refresh_tokens.discard(revoked)
    return {}


@app.get("/v1/userinfo")
def userinfo(authorization: str | None = Header(None)) -> dict[str, Any]:
    _authorised(authorization, "/v1/userinfo")
    return {**ACCOUNT, "email_verified": True}


@app.get("/gmail/v1/users/me/profile")
def profile(authorization: str | None = Header(None)) -> dict[str, Any]:
    _authorised(authorization, "/profile")
    return {"emailAddress": ACCOUNT["email"], "historyId": str(fake.history_id)}


@app.get("/gmail/v1/users/me/messages")
def list_messages(
    authorization: str | None = Header(None), maxResults: int = 100, pageToken: str = "", q: str = "",  # noqa: N803
) -> dict[str, Any]:  # fmt: skip
    _authorised(authorization, "/messages")
    newest_first = sorted(
        fake.messages.values(), key=lambda m: int(m["internalDate"]), reverse=True
    )
    start = int(pageToken or 0)
    page = newest_first[start : start + maxResults]
    listing: dict[str, Any] = {
        "messages": [{"id": m["id"], "threadId": m["threadId"]} for m in page]
    }
    if start + maxResults < len(newest_first):
        listing["nextPageToken"] = str(start + maxResults)
    return listing


@app.get("/gmail/v1/users/me/messages/{message_id}")
def get_message(message_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _authorised(authorization, f"/messages/{message_id}")
    if message_id not in fake.messages:
        raise HTTPException(404, "not found")
    return fake.messages[message_id]


@app.get("/gmail/v1/users/me/history")
def history(
    authorization: str | None = Header(None), startHistoryId: str = Query(...),  # noqa: N803
) -> dict[str, Any]:  # fmt: skip
    _authorised(authorization, "/history")
    if fake.forget_history:
        raise HTTPException(404, "startHistoryId too old")
    entries = [
        {"id": str(h), "messagesAdded": [{"message": {"id": m}}]}
        for h, m in fake.added
        if h > int(startHistoryId)
    ]
    return {"history": entries, "historyId": str(fake.history_id)}


@app.get("/calendar/v3/calendars/primary/events")
def events(
    authorization: str | None = Header(None), syncToken: str = "", timeMin: str = "",  # noqa: N803
) -> dict[str, Any]:  # fmt: skip
    _authorised(authorization, "/events")
    if syncToken:
        if fake.expire_sync_tokens:
            raise HTTPException(410, "sync token expired")
        since = int(syncToken.removeprefix("sync-"))
        items = [e for e in fake.events.values() if e.get("_changed_in", 1) > since]
    else:
        items = list(fake.events.values())
    visible = [{k: v for k, v in e.items() if not k.startswith("_")} for e in items]
    return {"items": visible, "nextSyncToken": f"sync-{fake.sync_generation}"}
