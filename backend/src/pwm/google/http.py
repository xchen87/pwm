"""Talking to Google: OAuth endpoints and authorised API calls with retries.

Every URL comes from settings, so tests and local development can point at a stand-in.
Nothing here logs or raises with response bodies: they can contain the user's mail.
"""

import base64
import hashlib
import secrets
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx

from pwm.config import Settings

SCOPES = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
)
# Google reports rate limits as 403 (rateLimitExceeded) as well as 429.
RETRYABLE = {403, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
MAX_WAIT_SECONDS = 30.0


class GoogleError(Exception):
    """A call to Google failed. Carries a status code, never a response body."""

    def __init__(self, status: int, what: str) -> None:
        super().__init__(f"{what} failed with {status}")
        self.status = status


class GrantRevoked(GoogleError):
    """The refresh token no longer works: the user revoked access, or it expired."""


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def authorization_url(settings: Settings, state: str, challenge: str) -> str:
    query = {
        "client_id": settings.google_client_id,
        "redirect_uri": callback_url(settings),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # offline + consent: the only combination that reliably returns a refresh token.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{settings.google_auth_url}?{urlencode(query)}"


def callback_url(settings: Settings) -> str:
    return settings.public_url.rstrip("/") + "/auth/google/callback"


class GoogleClient:
    def __init__(
        self,
        settings: Settings,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings, self._sleep = settings, sleep
        self._http = http or httpx.Client(timeout=30.0)

    # ---- OAuth

    def exchange_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": callback_url(self._settings),
            },
            "code exchange",
        )

    def refresh(self, refresh_token: str) -> str:
        granted = self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}, "token refresh"
        )
        return str(granted["access_token"])

    def _token_request(self, form: dict[str, str], what: str) -> dict[str, Any]:
        try:
            response = self._http.post(
                self._settings.google_token_url,
                data={
                    **form,
                    "client_id": self._settings.google_client_id or "",
                    "client_secret": self._settings.google_client_secret or "",
                },
            )
        except httpx.TransportError:
            raise GoogleError(0, what) from None
        if response.status_code == 200:
            granted: dict[str, Any] = response.json()
            return granted
        try:
            reason = str(response.json().get("error", ""))
        except ValueError:
            reason = ""
        # Only invalid_grant means the user's grant is gone (revoked, expired after 7 days in
        # "Testing", or a reused code). invalid_client, redirect_uri_mismatch and the rest
        # are our configuration, and must not be shown to users as "reconnect".
        if reason == "invalid_grant":
            raise GrantRevoked(response.status_code, what)
        raise GoogleError(response.status_code, what)

    def revoke(self, token: str) -> bool:
        """Whether Google confirmed the revocation. The local copy is destroyed regardless;
        the caller tells the user when Google could not be reached."""
        try:
            return self._http.post(
                self._settings.google_revoke_url, data={"token": token}
            ).is_success
        except httpx.HTTPError:
            return False

    def userinfo(self, access_token: str) -> dict[str, Any]:
        try:
            response = self._http.get(
                self._settings.google_userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.TransportError:
            raise GoogleError(0, "userinfo") from None
        if response.status_code != 200:
            raise GoogleError(response.status_code, "userinfo")
        info: dict[str, Any] = response.json()
        return info

    # ---- Authorised API calls

    def get(self, access_token: str, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET with bounded retries. 429 and 5xx back off (honouring Retry-After); anything
        else is the caller's to interpret via GoogleError.status."""
        url = self._settings.google_api_url.rstrip("/") + path
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._http.get(
                    url, params=params, headers={"Authorization": f"Bearer {access_token}"}
                )
            except httpx.TransportError:
                if attempt == MAX_ATTEMPTS:
                    raise GoogleError(0, f"GET {path}") from None
                self._sleep(min(2.0**attempt, MAX_WAIT_SECONDS))
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code in RETRYABLE and attempt < MAX_ATTEMPTS:
                wait = response.headers.get("Retry-After", "")
                delay = float(wait) if wait.replace(".", "", 1).isdigit() else 2.0**attempt
                self._sleep(min(delay, MAX_WAIT_SECONDS))
                continue
            raise GoogleError(response.status_code, f"GET {path}")
        raise GoogleError(0, f"GET {path}")
