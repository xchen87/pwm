"""Push notifications through Expo's push service.

A notification is a fixed generic title and a deep link, nothing else (threat model T8):
lock screens and Expo's servers see no names, amounts or quotes. The in-app inbox row is
written first, so a phone that is off still finds the notification when it opens the app.
Expo tokens that come back as dead (the app was uninstalled) are dropped.
"""

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm import clock
from pwm.db.models import Device, Notification, User

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
DEAD = {"DeviceNotRegistered"}


class ExpoPushNotifier:
    """Records the notification in the inbox, then asks Expo to deliver it to each device."""

    channel = "push"

    def __init__(self, http: httpx.Client | None = None, url: str = EXPO_PUSH_URL) -> None:
        self._http, self._url = http or httpx.Client(timeout=15.0), url

    def notify(self, session: Session, user: User, title: str, deep_link: str) -> None:
        session.add(
            Notification(
                user_id=user.id,
                title=title,
                deep_link=deep_link,
                channel=self.channel,
                created_at=clock.now(),
            )  # fmt: skip
        )
        devices = session.scalars(select(Device).where(Device.user_id == user.id)).all()
        if not devices:
            return
        messages: list[dict[str, Any]] = [
            {"to": d.push_token, "title": title, "data": {"url": deep_link}, "sound": "default"}
            for d in devices
        ]
        try:
            response = self._http.post(self._url, json=messages)
        except httpx.HTTPError:
            return  # the inbox row stands; push is best effort
        if response.status_code != 200:
            return
        tickets = response.json().get("data") or []
        for device, ticket in zip(devices, tickets, strict=False):
            details = ticket.get("details") or {}
            if ticket.get("status") == "error" and details.get("error") in DEAD:
                session.delete(device)
