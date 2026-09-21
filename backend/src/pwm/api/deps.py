from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm import auth
from pwm.config import get_settings
from pwm.db.models import User
from pwm.db.session import get_session
from pwm.pipeline.store import ensure_user
from pwm.sources import Party

DbSession = Annotated[Session, Depends(get_session)]


def current_user(session: DbSession, authorization: Annotated[str | None, Header()] = None) -> User:
    """Who is asking. Every handler gets the user from here and nowhere else.

    A valid session token always wins. Without one, the local development user is served
    only when the environment is "local" and dev login is on; anywhere else it is a 401,
    whatever rows exist.
    """
    settings = get_settings()
    if authorization:
        scheme, _, token = authorization.partition(" ")
        user = auth.user_for(session, token.strip()) if scheme.lower() == "bearer" else None
        if user is None:
            raise HTTPException(401, "sign in again")
        return user
    if not settings.is_local or not settings.dev_login:
        raise HTTPException(401, "sign in required")
    user = session.scalar(select(User).where(User.email == settings.dev_user_email))
    if user is None:
        user = ensure_user(
            session, Party(name=settings.dev_user_name, address=settings.dev_user_email)
        )
        session.commit()
    return user


CurrentUser = Annotated[User, Depends(current_user)]
