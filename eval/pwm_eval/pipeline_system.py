"""Runs the production funnel as a system under test."""

from collections.abc import Sequence
from datetime import date

from pwm.ask.answer import TemplateReasoner
from pwm.ask.facts import Fact
from pwm.ask.retrieval import retrieve
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
        self._context: dict[str, str] = {}

    def run(self, sources: Sequence[SourceRecord], user: Party) -> SystemOutput:
        result = self._result = run_pipeline(sources, user, self._triager, self._extractor)
        self._context = {
            s.id: f"{s.subject} {s.sender.name or s.sender.address if s.sender else ''}"
            for s in sources
        }
        kept: dict[str, list[Candidate]] = {o.source_id: [] for o in result.outcomes}
        for draft in result.assertions:
            kept[draft.candidate.source_id].append(draft.candidate)
        return SystemOutput(
            traces=tuple(
                SourceTrace(
                    source_id=o.source_id,
                    reached_model=o.reached_model,
                    extracted=o.reached_model and o.relevant is not False,
                    dropped_unverified=o.dropped_unverified + o.dropped_forbidden_origin,
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

    def ask(self, question: str, today: date) -> list[Candidate]:
        if self._result is None:
            return []
        drafts = self._result.assertions
        replaced = {
            r.from_index: r.to_index for r in self._result.relations if r.type == "supersedes"
        }
        facts = [
            Fact(
                id=str(index),
                kind=d.candidate.kind.value,
                subject=d.candidate.subject,
                predicate=d.candidate.predicate,
                value=d.candidate.value,
                evidence_quote=d.candidate.evidence_quote,
                context_words=self._context.get(d.candidate.source_id, ""),
                observed_at=d.observed_at,
                is_fact=d.candidate.kind.value == "memory",
                confidence=d.confidence.value,
                superseded=d.superseded_by is not None,
                previous_value=drafts[replaced[index]].candidate.value
                if index in replaced
                else None,
                commitment_type=d.candidate.commitment_type,
                direction=d.candidate.direction,
                committed_by=d.candidate.committed_by,
                committed_to=d.candidate.committed_to,
                due=d.candidate.due,
            )  # fmt: skip
            for index, d in enumerate(drafts)
            if d.confidence.value != "low"
        ]
        answer = TemplateReasoner().answer(question, retrieve(question, facts, today))
        return [drafts[int(f.id)].candidate for f in answer.cited]
