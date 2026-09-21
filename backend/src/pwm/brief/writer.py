"""Wording a brief. The writer words items; it never chooses or changes them."""

from typing import Protocol

from pydantic import BaseModel

from pwm.brief.items import BriefItem, ItemKind

PREDICATE_WORDS = {
    "date": "date",
    "phone": "phone number",
    "quote": "quote",
    "monthly_price": "monthly price",
    "monthly_rent": "monthly rent",
    "annual_premium": "annual premium",
    "return_window_ends": "return window",
    "expires": "expiry",
    "deadline": "deadline",
}


class WrittenItem(BaseModel):
    item: BriefItem
    headline: str
    why_it_matters: str
    suggested_next_step: str | None = None


class BriefWriter(Protocol):
    version: str

    def write(self, items: list[BriefItem]) -> list[WrittenItem]: ...


def _when(item: BriefItem) -> str:
    if item.due is None:
        return ""
    day = item.due.strftime("%a %b %-d")
    return f" — was due {day}" if item.overdue else f" — due {day}"


def _quoted(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class TemplateBriefWriter:
    """Deterministic wording with no model. Unconfirmed items are always worded as possibilities."""

    version = "template-v1"

    def write(self, items: list[BriefItem]) -> list[WrittenItem]:
        return [self._write(item) for item in items]

    def _write(self, item: BriefItem) -> WrittenItem:
        step: str | None
        what = PREDICATE_WORDS.get(item.predicate, item.predicate.replace("_", " "))
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
                headline = (
                    f"{item.subject}: {what} changed from {item.previous_value} to {item.value}"
                )
                why = "A later message updates what an earlier one said."
                step = None
            case ItemKind.CONFLICT:
                headline = (
                    f"Two sources disagree about {_quoted(item.subject, 60)}: "
                    f"{item.value} vs {item.previous_value}"
                )
                why = "I can't tell which is right, so both are shown."
                step = "Open it to see both sources."
            case ItemKind.CONSUMER:
                headline = f"{item.subject}: {what} {item.value}"
                why = "This takes effect soon and changes what you pay or can return."
                step = None
            case _:
                headline = f"You asked me to remember: {_quoted(item.evidence_quote)}"
                why = "The date you mentioned is coming up."
                step = None
        if not item.is_fact and item.kind in (ItemKind.CHANGED, ItemKind.CONSUMER):
            headline = f"It looks like {headline[0].lower()}{headline[1:]}"
        return WrittenItem(
            item=item, headline=headline, why_it_matters=why, suggested_next_step=step
        )
