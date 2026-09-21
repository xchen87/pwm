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


class SessionOut(BaseModel):
    token: str
    email: str
    name: str | None


class Me(BaseModel):
    email: str
    name: str | None
    signed_in_with_google: bool


@router.get("/auth/google/start")
def start(redirect: str, session: DbSession) -> RedirectResponse:
    try:
        url = auth.start(session, get_settings(), redirect)
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
    try:
        target = auth.finish(session, get_settings(), google, state, code)
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
        token = auth.redeem(session, get_settings(), body.code)
    except auth.AuthError as problem:
        session.commit()  # the code is spent either way
        raise HTTPException(400, str(problem)) from None
    user = auth.user_for(session, token)
    session.commit()
    assert user is not None
    return SessionOut(token=token, email=user.email, name=user.name)


@router.get("/auth/me")
def me(user: CurrentUser) -> Me:
    return Me(email=user.email, name=user.name, signed_in_with_google=user.google_sub is not None)


@router.post("/auth/logout")
def logout(
    session: DbSession, authorization: Annotated[str | None, Header()] = None
) -> dict[str, str]:
    if authorization and authorization.lower().startswith("bearer "):
        auth.sign_out(session, authorization[7:].strip())
        session.commit()
    return {"status": "signed out"}
