from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from pwm import auth
from pwm.api.deps import CurrentUser, DbSession
from pwm.config import get_settings
from pwm.google.http import GoogleClient, GoogleError

router = APIRouter()


def google_client() -> GoogleClient:
    return GoogleClient(get_settings())


Google = Annotated[GoogleClient, Depends(google_client)]


class LoginCodeIn(BaseModel):
    code: str = Field(min_length=10, max_length=200)
    verifier: str = Field(min_length=32, max_length=200)


class ConsentIn(BaseModel):
    terms_version: str = Field(max_length=32)
    age_confirmed: bool


class AuthConfig(BaseModel):
    google: bool
    # True only in local development: the API answers without a session.
    dev_login: bool
    terms_version: str
    minimum_age: int
    privacy_url: str
    terms_url: str


class SessionOut(BaseModel):
    token: str
    email: str
    name: str | None


class Me(BaseModel):
    email: str
    name: str | None
    signed_in_with_google: bool
    # False when the terms changed since this person accepted them. Until they accept the
    # new ones (POST /auth/consent) every other endpoint answers 403.
    terms_current: bool
    terms_version: str | None


@router.get("/auth/config")
def config() -> AuthConfig:
    """What a signed-out app needs to know to offer sign-in. Public by design."""
    settings = get_settings()
    base = settings.public_url.rstrip("/")
    return AuthConfig(
        google=settings.google_configured,
        dev_login=settings.is_local and settings.dev_login,
        terms_version=settings.terms_version,
        minimum_age=settings.minimum_age,
        privacy_url=f"{base}/legal/privacy",
        terms_url=f"{base}/legal/terms",
    )


@router.get("/auth/google/start")
def start(
    redirect: str, challenge: str, terms_version: str, age_confirmed: bool, session: DbSession
) -> RedirectResponse:
    try:
        consent = auth.Consent(terms_version, age_confirmed)
        url = auth.start(session, get_settings(), redirect, challenge, consent)
    except auth.AuthError as problem:
        raise HTTPException(400, str(problem)) from None
    session.commit()
    return RedirectResponse(url, status_code=302)


@router.get("/auth/google/callback")
def callback(
    session: DbSession, google: Google, state: str = "", code: str = "", error: str = ""
) -> RedirectResponse:
    if error or not state or not code:
        raise HTTPException(400, "sign-in was cancelled or did not complete")
    pending = auth.take_state(session, state)
    session.commit()  # spent before anything else happens, so it cannot be replayed
    if pending is None:
        raise HTTPException(400, "this sign-in attempt has expired; start again")
    try:
        target = auth.finish(session, get_settings(), google, pending, code)
    except auth.AuthError as problem:
        session.rollback()
        raise HTTPException(400, str(problem)) from None
    except GoogleError:
        session.rollback()
        raise HTTPException(502, "Google could not complete the sign-in. Try again.") from None
    session.commit()
    return RedirectResponse(target, status_code=302)


@router.post("/auth/session")
def create_session(body: LoginCodeIn, session: DbSession) -> SessionOut:
    try:
        token = auth.redeem(session, get_settings(), body.code, body.verifier)
    except auth.AuthError as problem:
        session.commit()  # the code is spent either way
        raise HTTPException(400, str(problem)) from None
    user = auth.user_for(session, token)
    session.commit()
    assert user is not None
    return SessionOut(token=token, email=user.email, name=user.name)


@router.get("/auth/me")
def me(user: CurrentUser) -> Me:
    return Me(
        email=user.email,
        name=user.name,
        signed_in_with_google=user.google_sub is not None,
        terms_current=auth.terms_current(get_settings(), user),
        terms_version=user.terms_version,
    )


@router.post("/auth/consent")
def accept_terms(body: ConsentIn, session: DbSession, user: CurrentUser) -> Me:
    """Accept changed terms from inside the app. The only thing a stale account may do
    besides read the terms, export its data, sign out or delete itself."""
    try:
        auth.record_consent(
            session, get_settings(), user, auth.Consent(body.terms_version, body.age_confirmed)
        )
    except auth.AuthError as problem:
        raise HTTPException(400, str(problem)) from None
    session.commit()
    return me(user)


@router.post("/auth/logout")
def logout(
    session: DbSession, authorization: Annotated[str | None, Header()] = None
) -> dict[str, str]:
    if authorization and authorization.lower().startswith("bearer "):
        auth.sign_out(session, authorization[7:].strip())
        session.commit()
    return {"status": "signed out"}
