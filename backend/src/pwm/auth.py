"""Sign-in with Google, and sessions.

The flow, for a phone or a browser alike:
1. The app opens the system browser at /auth/google/start?redirect=<its own URL>.
2. We remember a random `state` with a PKCE verifier and send the browser to Google.
3. Google sends it back to /auth/google/callback. We exchange the code, learn who it is,
   store the refresh token encrypted, and connect Gmail and Calendar.
4. The browser is sent back to the app with a single-use code, valid for two minutes.
5. The app exchanges that code for a session token over a direct request, presenting a
   secret whose hash it supplied in step 1.

So the session token never appears in a URL, a browser history, or a redirect log;
Google's tokens never leave the server at all; and the code in the redirect is useless to
anyone but the app instance that started the sign-in. That last point is what stops both
interception (another app registered for our URL scheme) and login CSRF (a link that
would sign the victim into the attacker's account): in either case the redeemer lacks the
secret.
"""

import hashlib
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pwm import clock, crypto
from pwm.config import Settings
from pwm.connectors.gcalendar import CalendarConnector
from pwm.connectors.gmail import GmailConnector
from pwm.connectors.service import connection_for, enqueue_sync
from pwm.db.models import AuthSession, LoginCode, OAuthState, OAuthToken, User
from pwm.google.http import SCOPES, GoogleClient, authorization_url, pkce_pair

STATE_LIFETIME = timedelta(minutes=10)
CODE_LIFETIME = timedelta(minutes=2)
_CHALLENGE = re.compile(r"[0-9a-f]{64}")  # hex SHA-256 of the app's secret


class AuthError(Exception):
    """Sign-in could not be completed. The message is safe to show."""


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def allowed_redirect(settings: Settings, target: str) -> bool:
    """Exact match on scheme, host and path against the allow-list. Prefix matching would let
    `pwm://auth.evil` or `https://app.example.com.evil` through, and whoever receives the
    redirect receives a login code."""
    # The raw string is what gets stored and redirected to, so the raw string is judged: no
    # "?", "#", whitespace or control characters (urlsplit would quietly drop some of them).
    if len(target) > 300 or re.search(r"[?#\s\x00-\x1f\\]", target):
        return False
    wanted = urlsplit(target)
    if wanted.username or wanted.password:
        return False
    for entry in settings.app_redirects:
        allowed = urlsplit(entry)
        if (wanted.scheme, wanted.netloc, wanted.path) == (
            allowed.scheme,
            allowed.netloc,
            allowed.path,
        ):
            return True
    # Expo Go serves a development build from whatever address the laptop has.
    return settings.is_local and wanted.scheme == "exp" and wanted.path.endswith("/--/auth")


def start(session: Session, settings: Settings, app_redirect: str, app_challenge: str) -> str:
    if not settings.google_configured:
        raise AuthError("Google sign-in is not configured")
    if not allowed_redirect(settings, app_redirect):
        raise AuthError("that redirect address is not allowed")
    if not _CHALLENGE.fullmatch(app_challenge):
        raise AuthError("a sign-in challenge is required")
    now = clock.now()
    session.execute(delete(OAuthState).where(OAuthState.created_at < now - STATE_LIFETIME))
    session.execute(delete(LoginCode).where(LoginCode.expires_at < now))
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    session.add(
        OAuthState(
            state=state,
            code_verifier=verifier,
            app_redirect=app_redirect,
            app_challenge=app_challenge,
            created_at=now,
        )  # fmt: skip
    )
    return authorization_url(settings, state, challenge)


def take_state(session: Session, state: str) -> OAuthState | None:
    """Fetch and spend a sign-in attempt. Spent means spent: the caller commits this before
    talking to Google, so a failed exchange cannot be retried with the same state."""
    pending = session.get(OAuthState, state)
    if pending is None:
        return None
    session.delete(pending)
    session.flush()
    session.expunge(pending)
    return pending if pending.created_at >= clock.now() - STATE_LIFETIME else None


def finish(
    session: Session, settings: Settings, google: GoogleClient, pending: OAuthState, code: str
) -> str:
    """Complete sign-in for an attempt already spent with `take_state`. Returns the app URL
    to send the browser to, carrying a login code only the starting app can redeem."""
    granted = google.exchange_code(code, pending.code_verifier)
    scopes = set(str(granted.get("scope", "")).split())
    missing = [s for s in SCOPES if s.startswith("https://") and s not in scopes]
    if missing:
        # We asked for access, were given less, and will not use it: hand it back rather
        # than leave a live grant at Google that nobody here holds.
        for unwanted in (granted.get("refresh_token"), granted.get("access_token")):
            if unwanted:
                google.revoke(str(unwanted))
        raise AuthError("read access to Gmail and Calendar was not granted")
    info = google.userinfo(str(granted["access_token"]))
    if not info.get("email_verified") or not info.get("sub") or not info.get("email"):
        raise AuthError("Google did not confirm this account's email address")

    user = _user_for_google(session, str(info["sub"]), str(info["email"]).lower(), info.get("name"))

    refresh_token = granted.get("refresh_token")
    stored = session.scalar(
        select(OAuthToken).where(OAuthToken.user_id == user.id, OAuthToken.provider == "google")
    )
    if refresh_token:
        sealed = crypto.encrypt(str(refresh_token), "google-refresh")
        if stored is None:
            session.add(
                OAuthToken(
                    user_id=user.id,
                    provider="google",
                    refresh_token_encrypted=sealed,
                    scopes=" ".join(sorted(scopes)),
                    created_at=clock.now(),
                )  # fmt: skip
            )
        else:
            stored.refresh_token_encrypted, stored.scopes = sealed, " ".join(sorted(scopes))
    elif stored is None:
        raise AuthError("Google did not provide offline access; remove the app's access and retry")

    for connector in (GmailConnector, CalendarConnector):
        connection = connection_for(session, user, connector)  # type: ignore[arg-type]
        connection.status, connection.last_error = "syncing", None
        enqueue_sync(session, user, connector.name)

    login_code = secrets.token_urlsafe(32)
    session.add(
        LoginCode(
            code_hash=_hash(login_code),
            user_id=user.id,
            app_challenge=pending.app_challenge,
            expires_at=clock.now() + CODE_LIFETIME,
        )  # fmt: skip
    )
    separator = "&" if "?" in pending.app_redirect else "?"
    return f"{pending.app_redirect}{separator}code={login_code}"


def _user_for_google(session: Session, sub: str, email: str, name: str | None) -> User:
    """Find or create the account for a Google identity.

    Google's account id decides, because an email address can change hands. An existing
    account with the same *verified* email that has never been linked to Google is adopted
    (in practice: the local development identity signing in for the first time). One that
    is linked to a different Google identity is never taken over.
    """
    user = session.scalar(select(User).where(User.google_sub == sub))
    if user is not None:
        return user
    same_email = session.scalar(select(User).where(User.email == email))
    if same_email is not None:
        if same_email.google_sub is not None:
            raise AuthError("this email address belongs to a different Google account here")
        same_email.google_sub = sub
        same_email.name = same_email.name or name
        return same_email
    user = User(email=email, name=name, google_sub=sub)
    session.add(user)
    session.flush()
    return user


def redeem(session: Session, settings: Settings, login_code: str, verifier: str) -> str:
    """Exchange a login code for a session token.

    The code works once, and only for whoever can show the secret whose hash was given when
    the sign-in started. So a code that leaks (another app registered for our URL scheme, a
    link an attacker sends) is useless to anyone but the app that began that sign-in, and
    an app cannot be tricked into redeeming a code from a sign-in it did not begin.
    """
    row = session.get(LoginCode, _hash(login_code))
    if row is None:
        raise AuthError("that sign-in code is not valid")
    session.delete(row)
    if row.expires_at < clock.now() or not secrets.compare_digest(
        row.app_challenge, _hash(verifier)
    ):
        raise AuthError("that sign-in code is not valid")
    token = secrets.token_urlsafe(48)
    session.add(
        AuthSession(
            user_id=row.user_id,
            token_hash=_hash(token),
            created_at=clock.now(),
            expires_at=clock.now() + timedelta(days=settings.session_days),
        )  # fmt: skip
    )
    return token


def user_for(session: Session, token: str) -> User | None:
    found = session.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
    if found is None or found.revoked_at is not None or found.expires_at < clock.now():
        return None
    return session.get(User, found.user_id)


def sign_out(session: Session, token: str) -> None:
    found = session.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
    if found is not None:
        found.revoked_at = clock.now()
