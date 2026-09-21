"""The seam between the eval harness and whatever is being evaluated.

A system under test receives only what production would see: source records and the
user's identity. It never sees gold labels (the oracle is the deliberate exception,
and exists to prove the metrics themselves are correct).
"""

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from pwm.extraction.candidates import Candidate
from pwm.extraction.interface import ModelUsage
from pwm.sources import Party, SourceKind, SourceRecord
from pwm_eval.gold import Gold, SourceCategory


class SourceTrace(BaseModel):
    """What happened to one source on its way through the funnel."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    reached_model: bool = False
    candidates: tuple[Candidate, ...] = ()
    usage: tuple[ModelUsage, ...] = ()


class ResolvedPerson(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    addresses: tuple[str, ...]


class PredictedRelation(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    from_candidate: Candidate
    to_candidate: Candidate


class SystemOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    traces: tuple[SourceTrace, ...]
    people: tuple[ResolvedPerson, ...] = ()
    relations: tuple[PredictedRelation, ...] = ()


class SystemUnderTest(Protocol):
    name: str

    def run(self, sources: Sequence[SourceRecord], user: Party) -> SystemOutput: ...

    def as_of(self, subject: str, predicate: str, when: date) -> str | None:
        """Answer a temporal query about the world built by the last `run`."""
        ...


class BaselineSystem:
    """Extracts nothing. Its scores are the floor every later change is compared with."""

    name = "baseline-null"

    def run(self, sources: Sequence[SourceRecord], user: Party) -> SystemOutput:
        return SystemOutput(traces=tuple(SourceTrace(source_id=s.id) for s in sources))

    def as_of(self, subject: str, predicate: str, when: date) -> str | None:
        return None


class OracleSystem:
    """Replays the gold labels. Must score perfectly; if it does not, the metrics are wrong."""

    name = "oracle"

    def __init__(self, gold: Gold) -> None:
        self._gold = gold

    def run(self, sources: Sequence[SourceRecord], user: Party) -> SystemOutput:
        traces = []
        for source in sources:
            candidates = tuple(
                Candidate.model_validate(a.model_dump(exclude={"id", "validity"}))
                for a in self._gold.assertions
                if a.source_id == source.id
            )
            needs_model = (
                source.kind is SourceKind.EMAIL
                and self._gold.categories[source.id] is not SourceCategory.NOISE
            )
            traces.append(
                SourceTrace(source_id=source.id, reached_model=needs_model, candidates=candidates)
            )
        people = tuple(
            ResolvedPerson(name=p.name, addresses=p.addresses) for p in self._gold.people
        )
        by_id = {
            a.id: Candidate.model_validate(a.model_dump(exclude={"id", "validity"}))
            for a in self._gold.assertions
        }
        relations = tuple(
            PredictedRelation(
                type=r.type.value, from_candidate=by_id[r.from_id], to_candidate=by_id[r.to_id]
            )
            for r in self._gold.relations
        )
        return SystemOutput(traces=tuple(traces), people=people, relations=relations)

    def as_of(self, subject: str, predicate: str, when: date) -> str | None:
        for q in self._gold.temporal_queries:
            if (q.subject, q.predicate, q.as_of) == (subject, predicate, when):
                return q.expected
        return None
