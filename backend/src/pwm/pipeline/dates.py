"""Resolve the date expressions people use in mail ("by Friday", "the 18th", "Sept 15")."""

import calendar
import re
from datetime import date, timedelta

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS |= {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name}
_MONTHS["sept"] = 9
_WEEKDAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}

_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_MONTH_DAY = re.compile(rf"\b({_MONTH})\.? (\d{{1,2}})(?:st|nd|rd|th)?(?:,? (\d{{4}}))?\b", re.I)
_ORDINAL = re.compile(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", re.I)
_WEEKDAY = re.compile(rf"\b(next )?({'|'.join(_WEEKDAYS)})\b", re.I)
_MONTH_ONLY = re.compile(rf"\bby (?:the end of )?({_MONTH})\b", re.I)
_SAME_DAY = re.compile(r"\b(tonight|today|this (?:evening|afternoon))\b", re.I)
_TOMORROW = re.compile(r"\btomorrow\b", re.I)


def _safe(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def resolve(text: str, written_on: date) -> date | None:
    """The first date expression in `text`, resolved forward from when it was written."""
    # "may" is a month only when capitalised: "you may 5 times retry" is not a date.
    month_days = (m for m in _MONTH_DAY.finditer(text) if m[1] != "may")
    if found := next(month_days, None):
        month, day = _MONTHS[found[1].lower()], int(found[2])
        if found[3]:
            return _safe(int(found[3]), month, day)
        this_year = _safe(written_on.year, month, day)
        if this_year and this_year >= written_on - timedelta(days=30):
            return this_year
        return _safe(written_on.year + 1, month, day)
    if found := _ORDINAL.search(text):
        day = int(found[1])
        this_month = _safe(written_on.year, written_on.month, day)
        if this_month and this_month >= written_on:
            return this_month
        year, month = divmod(written_on.month, 12)
        return _safe(written_on.year + year, month + 1, day)
    if _SAME_DAY.search(text):
        return written_on
    if _TOMORROW.search(text):
        return written_on + timedelta(days=1)
    if found := _WEEKDAY.search(text):
        ahead = (_WEEKDAYS[found[2].lower()] - written_on.weekday()) % 7 or 7
        # "next Friday" is the Friday of next week, not the one coming up.
        if found[1] and written_on.weekday() + ahead <= 6:
            ahead += 7
        return written_on + timedelta(days=ahead)
    if found := _MONTH_ONLY.search(text):
        month = _MONTHS[found[1].lower()]
        year = written_on.year if month >= written_on.month else written_on.year + 1
        return date(year, month, calendar.monthrange(year, month)[1])
    return None
