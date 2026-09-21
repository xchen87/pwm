"""One user's Google grant: holds the refresh token, hands out access tokens, and retries a
call once with a fresh token when Google says the old one expired."""

from typing import Any

from pwm.google.http import GoogleClient, GoogleError


class GoogleAccount:
    def __init__(self, client: GoogleClient, refresh_token: str) -> None:
        self._client, self._refresh_token = client, refresh_token
        self._access_token: str | None = None

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if self._access_token is None:
            self._access_token = self._client.refresh(self._refresh_token)
        try:
            return self._client.get(self._access_token, path, params)
        except GoogleError as error:
            if error.status != 401:
                raise
        # Access tokens last about an hour; a long backfill outlives one.
        self._access_token = self._client.refresh(self._refresh_token)
        return self._client.get(self._access_token, path, params)
