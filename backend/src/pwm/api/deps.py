from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm.config import get_settings
from pwm.db.models import User
from pwm.db.session import get_session

DbSession = Annotated[Session, Depends(get_session)]


def current_user(session: DbSession) -> User:
    """Local development identity. Slice 4 replaces this with real authentication;
    every handler already receives the user from here and nowhere else."""
    user = session.scalar(select(User).where(User.email == get_settings().dev_user_email))
    if user is None:
        raise HTTPException(503, "no local user yet: run `uv run python -m pwm.cli demo`")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
