"""The funnel (TECHNICAL_BRIEF §2). Pure: sources in, a reconciled world out.

Persistence and scheduling live elsewhere so the eval harness can run exactly the
code that production runs.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from pwm.extraction.candidates import Candidate, CandidateKind, Origin
from pwm.extraction.interface import ExtractionRequest, Extractor, ModelUsage, Triager
from pwm.extraction.quotes import quote_in_source
from pwm.pipeline.prefilter import Route, is_from_user, route
from pwm.pipeline.resolution import ResolvedIdentity, is_user_lookalike, resolve_people
from pwm.pipeline.text import looks_like_injection, visible_text
from pwm.pipeline.world import DraftAssertion, DraftRelation, assign_confidence, reconcile
from pwm.sources import Party, SourceKind, SourceRecord


class SourceOutcome(BaseModel):
    source_id: str
    route: Route
    reached_model: bool = False
    relevant: bool | None = None
    suspicious: bool = False
    dropped_unverified: int = 0
    dropped_forbidden_origin: int = 0
    usage: tuple[ModelUsage, ...] = ()


class PipelineResult(BaseModel):
    outcomes: list[SourceOutcome]
    assertions: list[DraftAssertion]
    relations: list[DraftRelation]
    people: tuple[ResolvedIdentity, ...]


def calendar_candidate(source: SourceRecord) -> Candidate | None:
    if source.starts_at is None or not source.subject:
        return None
    return Candidate(
        source_id=source.id,
        kind=CandidateKind.EVENT,
        subject=source.subject,
        predicate="date",
        value=source.starts_at.strftime("%Y-%m-%dT%H:%M"),
        evidence_quote=source.subject,
        origin=Origin.SOURCE_EXPLICIT,
    )


def acceptable(
    candidate: Candidate, source: SourceRecord, text: str, outcome: SourceOutcome
) -> bool:
    """Stage 5. The gate every model output passes through before it can be stored."""
    if candidate.source_id != source.id or not quote_in_source(candidate.evidence_quote, text):
        outcome.dropped_unverified += 1
        return False
    # Only the user can state something, and only through the app.
    if candidate.origin is Origin.USER_STATED and source.kind is not SourceKind.USER_CAPTURE:
        outcome.dropped_forbidden_origin += 1
        return False
    return True


def run_pipeline(
    sources: Sequence[SourceRecord], user: Party, triager: Triager, extractor: Extractor
) -> PipelineResult:
    ordered = sorted(sources, key=lambda s: (s.observed_at, s.id))
    people = resolve_people(ordered, user)
    known_addresses = {address for person in people for address in person.addresses}
    thread_history: dict[str, list[str]] = {}
    outcomes: list[SourceOutcome] = []
    drafts: list[DraftAssertion] = []

    for source in ordered:
        decision = route(source, user)
        outcome = SourceOutcome(source_id=source.id, route=decision)
        outcomes.append(outcome)
        text = visible_text(source)
        candidates: tuple[Candidate, ...] = ()

        if decision is Route.STRUCTURED:
            event = calendar_candidate(source)
            candidates = (event,) if event else ()
        elif decision in (Route.TRIAGE, Route.EXTRACT):
            request = ExtractionRequest(
                source=source,
                visible_text=text,
                context=tuple(thread_history.get(source.thread_id or "", ())),
                user=user,
            )
            outcome.reached_model = True
            relevant = True
            if decision is Route.TRIAGE:
                triage = triager.is_relevant(request)
                outcome.usage += triage.usage
                relevant = outcome.relevant = triage.relevant
            if relevant:
                extraction = extractor.extract(request)
                outcome.usage += extraction.usage
                outcome.suspicious = extraction.suspicious_content
                candidates = extraction.candidates
        if source.thread_id and decision is not Route.SKIP:
            thread_history.setdefault(source.thread_id, []).append(text)

        sender = source.sender
        outcome.suspicious = (
            outcome.suspicious
            or looks_like_injection(source.body)
            or (sender is not None and is_user_lookalike(sender, user))
        )
        structured = decision is Route.STRUCTURED
        for candidate in candidates:
            if not acceptable(candidate, source, text, outcome):
                continue
            drafts.append(
                DraftAssertion(
                    candidate=candidate,
                    observed_at=source.observed_at,
                    thread_id=source.thread_id,
                    sender_address=sender.address.lower() if sender else None,
                    extraction_method="calendar" if structured else extractor.method,
                    prompt_version="structured-v1" if structured else extractor.prompt_version,
                    confidence=assign_confidence(
                        candidate,
                        sender_known=sender is not None
                        and sender.address.lower() in known_addresses,
                        sender_is_user=is_from_user(source, user),
                        suspicious=outcome.suspicious,
                    ),
                )
            )

    return PipelineResult(
        outcomes=outcomes, assertions=drafts, relations=reconcile(drafts), people=people
    )
