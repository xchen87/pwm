from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from pwm import clock
from pwm.api.deps import CurrentUser, DbSession
from pwm.db.models import Device

router = APIRouter()
MAX_DEVICES = 5


class DeviceIn(BaseModel):
    # Expo push tokens look like ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx].
    push_token: str = Field(
        min_length=10, max_length=200, pattern=r"^Expo(nent)?PushToken\[[\w-]+\]$"
    )
    platform: str = Field(pattern=r"^(ios|android)$")


@router.post("/devices")
def register(body: DeviceIn, session: DbSession, user: CurrentUser) -> dict[str, str]:
    """Called whenever the app has a push token: on first run and after every reinstall."""
    # A phone belongs to whoever is signed in on it now. Rows another account left behind
    # (a sign-out that never reached the server) would make this phone buzz for that account.
    session.execute(
        delete(Device).where(Device.push_token == body.push_token, Device.user_id != user.id)
    )
    device = session.scalar(
        select(Device).where(Device.user_id == user.id, Device.push_token == body.push_token)
    )
    if device is None:
        # Bounded: the oldest devices make room. Nobody carries more than a few phones.
        others = session.scalars(
            select(Device).where(Device.user_id == user.id).order_by(Device.last_seen_at.desc())
        ).all()
        for stale in others[MAX_DEVICES - 1 :]:
            session.delete(stale)
        device = Device(
            user_id=user.id, push_token=body.push_token, platform=body.platform,
            registered_at=clock.now(), last_seen_at=clock.now(),
        )  # fmt: skip
        session.add(device)
    device.last_seen_at = clock.now()
    session.commit()
    return {"status": "registered"}


@router.delete("/devices")
def unregister(body: DeviceIn, session: DbSession, user: CurrentUser) -> dict[str, str]:
    """On sign-out: this phone must not receive this account's notifications any more."""
    gone = session.execute(
        delete(Device)
        .where(Device.user_id == user.id, Device.push_token == body.push_token)
        .returning(Device.id)
    ).all()
    session.commit()
    if not gone:
        raise HTTPException(404, "not registered")
    return {"status": "unregistered"}
