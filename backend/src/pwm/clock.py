"""The one place that knows what time it is.

`PWM_FIXED_NOW` pins the clock so the synthetic mailbox (which lives in September 2026)
can be demonstrated on any day without every item reading as months overdue.
"""

from datetime import UTC, date, datetime

from pwm.config import get_settings


def now() -> datetime:
    fixed = get_settings().fixed_now
    if fixed is None:
        return datetime.now(UTC)
    return fixed if fixed.tzinfo else fixed.replace(tzinfo=UTC)


def today() -> date:
    return now().date()
