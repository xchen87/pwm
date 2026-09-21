"""Finding the facts that bear on a question. Plain code, no model.

Runs in process over one user's live assertions, which is ample at MVP scale. Postgres
full-text search and pgvector take over behind the same function when a mailbox
outgrows this (decisions D37).
"""

import re
from collections.abc import Sequence
from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel

from pwm.ask.facts import Fact

_STOPWORDS = frozenset(
    "a an and are as at be been by did do does for from had has have how i if in is it its me my "
    "of on or our so that the their them then there these they this to up was we were what when "
    "where which who whom why will with you your about again now still any all much many going "
    "supposed am im ive say said tell know".split()
)
MAX_RESULTS = 6
MIN_SCORE = 1.0


class Intent(StrEnum):
    MY_COMMITMENTS = "my_commitments"
    OWED_TO_ME = "owed_to_me"
    DEADLINES = "deadlines"
    DECISION = "decision"
    WHEN = "when"
    HISTORY = "history"
    LOOKUP = "lookup"


class Retrieved(BaseModel):
    intent: Intent
    facts: list[Fact]
    # Set when the question named someone or something nothing is known about.
    unknown_terms: list[str] = []


def words(text: str) -> list[str]:
    return [
        w for w in re.findall(r"[a-z0-9]+", text.lower().replace("'", "")) if w not in _STOPWORDS
    ]


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


# Question words that describe the kind of answer wanted, not what it is about.
_GENERIC = frozenset(
    _stem(w)
    for w in (
        "promise promised owe owes commit committed commitment commitments deadline deadlines due "
        "decide decided decision chose choose reason original originally number coming come week "
        "next much going agree agreed pay send new now current currently happen happening"
    ).split()
)


def detect_intent(question: str) -> Intent:
    q = question.lower()
    if re.search(r"\bwhy\b|\bdecide|\bdecision|\bchose\b|\bchoose\b|\breason", q):
        return Intent.DECISION
    if re.search(r"\b(originally|used to|before|previously|at first|was the)\b", q):
        return Intent.HISTORY
    if re.search(r"\bdeadlines?\b|\bdue\b|\bcoming up\b|\bthis week\b|\bnext week\b", q):
        return Intent.DEADLINES
    if re.search(
        r"\b(did|do|have) i (promise|owe|commit|agree|say)|\bi (promised|owe)\b|\bmy commitments\b",
        q,
    ):
        return Intent.MY_COMMITMENTS
    if re.search(
        r"\b(owes? me|promised? me|supposed to|waiting (on|for)|send me|get back to me)\b", q
    ):
        return Intent.OWED_TO_ME
    if re.search(r"^\s*when\b|\bwhat time\b|\bwhat day\b", q):
        return Intent.WHEN
    return Intent.LOOKUP


def _searchable(fact: Fact) -> dict[str, float]:
    """Stemmed words of a fact with a weight: what it says counts more than where it was said."""
    weights: dict[str, float] = {}
    fields = (
        (f"{fact.subject} {fact.value} {fact.committed_by or ''} {fact.committed_to or ''}", 2.0),
        (fact.evidence_quote, 1.5),
        (f"{fact.context_words} {fact.predicate.replace('_', ' ')}", 1.0),
    )
    for text, weight in fields:
        for word in words(text):
            stem = _stem(word)
            weights[stem] = max(weights.get(stem, 0.0), weight)
    return weights


def _matches_intent(fact: Fact, intent: Intent) -> bool:
    match intent:
        case Intent.MY_COMMITMENTS:
            return fact.kind == "commitment" and fact.direction == "by_user"
        case Intent.OWED_TO_ME:
            return fact.kind == "commitment" and fact.direction == "to_user"
        case Intent.DEADLINES:
            return fact.kind == "commitment" and fact.due is not None
        case Intent.DECISION:
            return fact.kind == "decision"
        case Intent.WHEN:
            return fact.predicate in ("date", "deadline") or fact.due is not None
        case _:
            return True


def retrieve(question: str, facts: Sequence[Fact], today: date) -> Retrieved:
    intent = detect_intent(question)
    terms = [s for s in (_stem(w) for w in words(question)) if s not in _GENERIC]
    everything = {t for f in facts for t in _searchable(f)}
    unknown = [t for t in terms if t not in everything]
    if unknown:
        # The question is about someone or something that appears nowhere. Answering from
        # the words that do match ("insurance", for a boat that does not exist) would be a
        # confident answer to a different question.
        return Retrieved(intent=intent, facts=[], unknown_terms=unknown)

    live = [f for f in facts if intent is Intent.HISTORY or not f.superseded]
    pool = [f for f in live if _matches_intent(f, intent)]

    scored: list[tuple[float, Fact]] = []
    known_terms: set[str] = set()
    for fact in pool:
        searchable = _searchable(fact)
        hits = [t for t in terms if t in searchable]
        known_terms.update(hits)
        score = sum(searchable[t] for t in hits)
        if terms and len(hits) * 2 < len(terms):
            continue  # most of what was asked about has to be there
        if intent is Intent.HISTORY and fact.superseded:
            score += 2.0
        if fact.is_fact:
            score += 0.5
        if score >= MIN_SCORE or not terms:
            scored.append((score, fact))

    if intent is Intent.DEADLINES and not terms:
        earliest, latest = today - timedelta(days=7), today + timedelta(days=21)
        upcoming = [
            f for f in pool if f.due and earliest <= f.due <= latest and f.status in (None, "open")
        ]
        ordered = sorted(upcoming, key=lambda f: f.due or date.max)
    else:
        ordered = [
            f for _, f in sorted(scored, key=lambda s: (-s[0], -s[1].observed_at.timestamp()))
        ]

    return Retrieved(intent=intent, facts=ordered[:MAX_RESULTS])
