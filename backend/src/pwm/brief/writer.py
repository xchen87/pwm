"""Wording a brief. The writer words items; it never chooses or changes them."""

import math
from datetime import date, datetime
from typing import Protocol

from pydantic import BaseModel

from pwm.brief.items import BriefItem, ItemKind


class WrittenItem(BaseModel):
    item: BriefItem
    headline: str
    why_it_matters: str
    suggested_next_step: str | None = None


class BriefWriter(Protocol):
    version: str

    def write(self, items: list[BriefItem]) -> list[WrittenItem]: ...


MONEY = {"quote", "monthly_price", "monthly_rent", "annual_premium"}
PER = {"monthly_price": " a month", "monthly_rent": " a month", "annual_premium": " a year"}


def _day(value: date) -> str:
    return value.strftime("%a, %b %-d")


def _when(item: BriefItem) -> str:
    if item.due is None:
        return ""
    return f" — was due {_day(item.due)}" if item.overdue else f" — due {_day(item.due)}"


def _quoted(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def readable(predicate: str, value: str | None) -> str:
    """Dates and amounts the way a person would write them. Anything else is left alone."""
    if not value:
        return "unknown"
    if predicate in MONEY:
        try:
            amount = float(value)
            if not math.isfinite(amount):
                return value
            whole = amount == int(amount)
        except (ValueError, OverflowError):
            return value
        return f"${int(amount):,}" if whole else f"${amount:,.2f}"
    try:
        if "T" in value:
            moment = datetime.fromisoformat(value)
            return f"{_day(moment.date())} at {moment.strftime('%-I:%M %p')}"
        return _day(date.fromisoformat(value))
    except ValueError:
        return value


class TemplateBriefWriter:
    """Deterministic wording with no model. Unconfirmed items are always worded as possibilities."""

    version = "template-v1"

    def write(self, items: list[BriefItem]) -> list[WrittenItem]:
        return [self._write(item) for item in items]

    def _write(self, item: BriefItem) -> WrittenItem:
        step: str | None
        match item.kind:
            case ItemKind.DUE_SOON:
                headline = f"{_quoted(item.value)}{_when(item)}"
                why = (
                    "You confirmed this, and the date is close."
                    if not item.overdue
                    else ("You confirmed this and the date has passed.")
                )
                step = "Mark it done when it is, or edit the date."
            case ItemKind.POSSIBLE_COMMITMENT:
                headline = f"Possible commitment: {_quoted(item.value)}{_when(item)}"
                why = "It looks like a promise or deadline, but I have not tracked it."
                step = "Confirm it to track it, or dismiss it."
            case ItemKind.CHANGED:
                new, old = (
                    readable(item.predicate, item.value),
                    readable(item.predicate, item.previous_value),
                )
                if item.predicate in MONEY:
                    headline = f"{item.subject}: now {new}, was {old}"
                else:
                    headline = f"{item.subject}: moved to {new} (was {old})"
                why = "A later message updates what an earlier one said."
                step = None
            case ItemKind.CONFLICT:
                new, old = (
                    readable(item.predicate, item.value),
                    readable(item.predicate, item.previous_value),
                )
                headline = f"Two sources disagree about {_quoted(item.subject, 60)}: {new} or {old}"
                why = "I can’t tell which is right, so both are shown."
                step = "Open it to see both sources."
            case ItemKind.CONSUMER:
                amount = readable(item.predicate, item.value)
                starts = f" from {_day(item.effective)}" if item.effective else ""
                if item.predicate == "return_window_ends":
                    headline = f"{item.subject}: you can return it until {amount}"
                    why = "After that date it can’t go back."
                else:
                    headline = f"{item.subject}: {amount}{PER.get(item.predicate, '')}{starts}"
                    why = "This changes what you pay, and it starts soon."
                step = None
            case _:
                headline = f"You asked me to remember: {_quoted(item.evidence_quote)}"
                why = "The date you mentioned is coming up."
                step = None
        if not item.is_fact and item.kind in (ItemKind.CHANGED, ItemKind.CONSUMER):
            headline = f"It looks like {headline}"
        return WrittenItem(
            item=item, headline=headline, why_it_matters=why, suggested_next_step=step
        )
