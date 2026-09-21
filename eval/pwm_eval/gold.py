"""Gold labels for evaluation fixtures.

Labels follow the three independent axes in TECHNICAL_BRIEF §4. `review` is absent on
purpose: pipeline output is always unreviewed, and only a user can change that.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from pwm.extraction.candidates import Candidate
from pwm.sources import Party


class SourceCategory(StrEnum):
    SIGNAL = "signal"
    # Machine-sent mail that still matters (price change, renewal, return window).
    # A prefilter that drops all automated mail fails on these.
    AUTOMATED_SIGNAL = "automated_signal"
    NOISE = "noise"
    ADVERSARIAL = "adversarial"


class Validity(StrEnum):
    """Whether the assertion still holds at the fixture's as-of date."""

    CURRENT = "current"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class RelationType(StrEnum):
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"


class GoldAssertion(Candidate):
    id: str
    validity: Validity = Validity.CURRENT


class GoldRelation(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: RelationType
    from_id: str
    to_id: str


class GoldPerson(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    addresses: tuple[str, ...]


class TemporalQuery(BaseModel):
    """What did the world look like on `as_of`? `expected` is compared after normalization."""

    model_config = ConfigDict(frozen=True)

    id: str
    subject: str
    predicate: str
    as_of: date
    expected: str


class GoldQuestion(BaseModel):
    """A question for Ask Your World. `expected` lists gold assertions any one of which
    makes the answer right; an empty list means the only right answer is a refusal."""

    model_config = ConfigDict(frozen=True)

    id: str
    question: str
    expected: tuple[str, ...] = ()


class InjectedSpan(BaseModel):
    """Attacker-written text. No candidate may be derived from it."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    text: str


class Gold(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    user: Party
    categories: dict[str, SourceCategory]
    assertions: tuple[GoldAssertion, ...]
    relations: tuple[GoldRelation, ...]
    people: tuple[GoldPerson, ...]
    temporal_queries: tuple[TemporalQuery, ...]
    injected_spans: tuple[InjectedSpan, ...]
    questions: tuple[GoldQuestion, ...] = ()
