"""Wording an answer from retrieved facts. The reasoner cannot add facts: it receives
evidence and must cite it, and an answer with no evidence is a refusal."""

from typing import Protocol

from pydantic import BaseModel

from pwm.ask.facts import Fact
from pwm.ask.retrieval import Intent, Retrieved

NOTHING_KNOWN = "I don’t have anything about that in what I’ve seen."


class Answer(BaseModel):
    text: str
    grounded: bool
    cited: list[Fact]
    caveat: str | None = None


class Reasoner(Protocol):
    version: str

    def answer(self, question: str, retrieved: Retrieved) -> Answer: ...


def _date(fact: Fact) -> str:
    return f" (due {fact.due.strftime('%a %b %-d')})" if fact.due else ""


def _line(fact: Fact) -> str:
    # Something that was later replaced is history, however it was reviewed at the time.
    if fact.superseded:
        hedge, old = "Earlier: ", " — later replaced"
    else:
        hedge, old = ("" if fact.is_fact else "Possibly: "), ""
    if fact.kind == "commitment":
        who = "you" if fact.direction == "by_user" else (fact.committed_by or "someone")
        return f"{hedge}{who}: {fact.value}{_date(fact)}{old}"
    if fact.kind == "decision":
        return f"{hedge}{fact.evidence_quote}{old}"
    if fact.kind == "memory":
        return f"You told me: {fact.value}"
    change = f" (previously {fact.previous_value})" if fact.previous_value else ""
    return f"{hedge}{fact.subject} — {fact.predicate.replace('_', ' ')}: {fact.value}{change}{old}"


class TemplateReasoner:
    """Deterministic answers with no model: a lead sentence, then the evidence, hedged
    unless the user confirmed it."""

    version = "template-v1"

    LEADS = {
        Intent.MY_COMMITMENTS: "Here is what it looks like you’ve committed to:",
        Intent.OWED_TO_ME: "Here is what others appear to owe you:",
        Intent.DEADLINES: "Here are the dates I know about:",
        Intent.DECISION: "Here is what I found about that decision:",
        Intent.WHEN: "Here is what I have on timing:",
        Intent.HISTORY: "Here is how that has changed:",
        Intent.LOOKUP: "Here is what I found:",
    }

    def answer(self, question: str, retrieved: Retrieved) -> Answer:
        if not retrieved.facts:
            text = NOTHING_KNOWN
            if retrieved.unknown_terms:
                text = f"I haven’t seen anything about “{retrieved.unknown_terms[0]}”."
            return Answer(text=text, grounded=False, cited=[])
        lines = "\n".join(f"• {_line(f)}" for f in retrieved.facts)
        unconfirmed = [f for f in retrieved.facts if not f.is_fact]
        notes = []
        if retrieved.corrections:
            typed, read_as = retrieved.corrections[0]
            notes.append(f"I read “{typed}” as “{read_as}”.")
        if unconfirmed:
            notes.append(
                "Some of this comes from messages and hasn’t been confirmed by you. "
                "Open an item to see its source."
            )
        caveat = " ".join(notes) or None
        return Answer(
            text=f"{self.LEADS[retrieved.intent]}\n{lines}",
            grounded=True,
            cited=list(retrieved.facts),
            caveat=caveat,
        )
