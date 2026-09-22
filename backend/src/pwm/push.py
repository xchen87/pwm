"""Push notifications through Expo's push service.

A notification is a fixed generic title and a deep link, nothing else (threat model T8):
lock screens and Expo's servers see no names, amounts or quotes. The in-app inbox row is
written first, so a phone that is off still finds the notification when it opens the app.

Delivery is best effort and audited by outcome, never by content: what is logged is a
count, a status code, or Expo's error name. Tokens Expo reports dead in the ticket are
dropped at once. Expo reports most delivery failures later, in receipts, which are not
fetched yet; a dead device is therefore dropped one push late, and Expo tolerates that.
"""

import logging
from collections.abc import Sequence
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm import clock
from pwm.db.models import Device, Notification, User

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
DEAD = {"DeviceNotRegistered"}
BATCH = 100  # Expo's limit per request
log = logging.getLogger("pwm.push")
_shared = httpx.Client(timeout=5.0)


class ExpoPushNotifier:
    """Records the notification in the inbox, then asks Expo to deliver it to each device."""

    channel = "push"

    def __init__(self, http: httpx.Client | None = None, url: str = EXPO_PUSH_URL) -> None:
        self._http, self._url = http or _shared, url

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
        for start in range(0, len(devices), BATCH):
            self._send(session, devices[start : start + BATCH], title, deep_link)

    def _send(
        self, session: Session, devices: Sequence[Device], title: str, deep_link: str
    ) -> None:
        messages: list[dict[str, Any]] = [
            {
                "to": d.push_token,
                "title": title,
                "data": {"url": deep_link},
                "sound": "default",
                "channelId": "default",
            }
            for d in devices
        ]
        try:
            response = self._http.post(self._url, json=messages)
            tickets = response.json().get("data") if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            log.warning("push: Expo unreachable or unreadable; %d device(s) not told", len(devices))
            return  # the inbox row stands
        if not isinstance(tickets, list):
            log.warning(
                "push: Expo answered %s; %d device(s) not told", response.status_code, len(devices)
            )
            return
        dropped = 0
        for device, ticket in zip(devices, tickets, strict=False):
            if not isinstance(ticket, dict) or ticket.get("status") != "error":
                continue
            reason = str((ticket.get("details") or {}).get("error") or "unknown")
            if reason in DEAD:
                session.delete(device)
                dropped += 1
            else:
                log.warning("push: ticket error %s", reason)
        log.info("push: %d device(s), %d dropped as dead", len(devices), dropped)
