from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm.config import get_settings
from pwm.db.models import User
from pwm.db.session import get_session
from pwm.pipeline.store import ensure_user
from pwm.sources import Party

DbSession = Annotated[Session, Depends(get_session)]


def current_user(session: DbSession) -> User:
    """Local development identity. Slice 4 replaces this with real authentication;
    every handler already receives the user from here and nowhere else."""
    settings = get_settings()
    user = session.scalar(select(User).where(User.email == settings.dev_user_email))
    if user is None:
        if settings.environment != "local":
            raise HTTPException(401, "sign in required")
        user = ensure_user(
            session, Party(name=settings.dev_user_name, address=settings.dev_user_email)
        )
        session.commit()
    return user


CurrentUser = Annotated[User, Depends(current_user)]
