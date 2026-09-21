"""Runs the production funnel as a system under test."""

from collections.abc import Sequence
from datetime import date

from pwm.extraction.candidates import Candidate
from pwm.extraction.interface import Extractor, Triager
from pwm.pipeline.core import PipelineResult, run_pipeline
from pwm.pipeline.world import as_of
from pwm.sources import Party, SourceRecord
from pwm_eval.systems import PredictedRelation, ResolvedPerson, SourceTrace, SystemOutput


class PipelineSystem:
    def __init__(self, name: str, triager: Triager, extractor: Extractor) -> None:
        self.name = name
        self._triager = triager
        self._extractor = extractor
        self._result: PipelineResult | None = None

    def run(self, sources: Sequence[SourceRecord], user: Party) -> SystemOutput:
        result = self._result = run_pipeline(sources, user, self._triager, self._extractor)
        kept: dict[str, list[Candidate]] = {o.source_id: [] for o in result.outcomes}
        for draft in result.assertions:
            kept[draft.candidate.source_id].append(draft.candidate)
        return SystemOutput(
            traces=tuple(
                SourceTrace(
                    source_id=o.source_id,
                    reached_model=o.reached_model,
                    candidates=tuple(kept[o.source_id]),
                    usage=o.usage,
                )
                for o in result.outcomes
            ),
            people=tuple(ResolvedPerson(name=p.name, addresses=p.addresses) for p in result.people),
            relations=tuple(
                PredictedRelation(
                    type=r.type.value,
                    from_candidate=result.assertions[r.from_index].candidate,
                    to_candidate=result.assertions[r.to_index].candidate,
                )
                for r in result.relations
            ),
        )

    def as_of(self, subject: str, predicate: str, when: date) -> str | None:
        return as_of(self._result.assertions, subject, predicate, when) if self._result else None
