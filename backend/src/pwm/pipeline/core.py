"""The funnel (TECHNICAL_BRIEF §2). Pure: sources in, a reconciled world out.

Persistence and scheduling live elsewhere so the eval harness can run exactly the
code that production runs.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from pwm.extraction.candidates import Candidate, CandidateKind, Origin
from pwm.extraction.interface import ExtractionRequest, Extractor, ModelUsage, Triager
from pwm.extraction.quotes import quote_in_source
from pwm.pipeline.prefilter import Route, is_from_user, route
from pwm.pipeline.resolution import ResolvedIdentity, is_user_lookalike, resolve_people
from pwm.pipeline.text import looks_like_injection, visible_text
from pwm.pipeline.world import DraftAssertion, DraftRelation, assign_confidence, reconcile
from pwm.sources import Party, SourceKind, SourceRecord

SUBJECT_LIMIT, VALUE_LIMIT, QUOTE_LIMIT = 300, 2000, 1000


class SourceOutcome(BaseModel):
    source_id: str
    route: Route
    reached_model: bool = False
    relevant: bool | None = None
    suspicious: bool = False
    dropped_unverified: int = 0
    dropped_forbidden_origin: int = 0
    # The name of the error if this one source could not be processed. Never its text.
    failed: str | None = None
    usage: tuple[ModelUsage, ...] = ()


class PipelineResult(BaseModel):
    outcomes: list[SourceOutcome]
    assertions: list[DraftAssertion]
    relations: list[DraftRelation]
    people: tuple[ResolvedIdentity, ...]


def silenced_calendar_versions(sources: Sequence[SourceRecord]) -> set[str]:
    """Calendar sources that must not assert anything.

    An edited event is a new immutable source whose id is `<event>@<updated>`. For each
    event: a cancelled latest version silences every version (the event is off); otherwise
    an older version is silenced when the next one says the same time, so an edit to the
    description or an RSVP does not leave two identical events. A version with a
    *different* time keeps its voice, which is how a moved meeting shows up as a change.
    """
    versions: dict[str, list[SourceRecord]] = {}
    for source in sources:
        if source.kind is SourceKind.CALENDAR_EVENT:
            versions.setdefault(source.id.split("@")[0], []).append(source)
    silenced: set[str] = set()
    for history in versions.values():
        history.sort(key=lambda s: s.observed_at)
        if history[-1].event_status == "cancelled":
            silenced.update(s.id for s in history)
            continue
        for older, newer in zip(history, history[1:], strict=False):
            if older.event_status == "cancelled" or older.starts_at == newer.starts_at:
                silenced.add(older.id)
    return silenced


def calendar_candidate(source: SourceRecord) -> Candidate | None:
    if source.starts_at is None or not source.subject.strip():
        return None
    title = source.subject.strip()[:SUBJECT_LIMIT]
    return Candidate(
        source_id=source.id,
        kind=CandidateKind.EVENT,
        subject=title,
        predicate="date",
        value=source.starts_at.strftime("%Y-%m-%dT%H:%M"),
        evidence_quote=title,
        origin=Origin.SOURCE_EXPLICIT,
    )


def memory_candidate(source: SourceRecord) -> Candidate:
    text = source.body.strip()
    return Candidate(
        source_id=source.id,
        kind=CandidateKind.MEMORY,
        subject="Note",
        predicate="note",
        value=text[:VALUE_LIMIT],
        # Evidence is a passage, so a long note is evidenced by its opening.
        evidence_quote=text[:QUOTE_LIMIT],
        origin=Origin.USER_STATED,
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


_COMMENT = re.compile(r"\([^()]*\)")
_VERDICT = re.compile(r"\b(dmarc|spf|dkim)\s*=\s*(\w+)", re.I)


def failed_sender_authentication(source: SourceRecord) -> bool:
    """Whether the receiving mail server (Gmail) recorded that this message's From address is
    probably forged: DMARC failed, or, where there is no DMARC verdict, both SPF and DKIM
    failed outright. A DMARC pass settles it the other way, which is what keeps ordinary
    forwarded and mailing-list mail (one check fails, DMARC passes) from being flagged.
    Absent results prove nothing either way."""
    results = next(
        (v for k, v in source.headers.items() if k.lower() == "authentication-results"), ""
    )
    verdicts: dict[str, set[str]] = {}
    for method, verdict in _VERDICT.findall(_COMMENT.sub(" ", results)):
        verdicts.setdefault(method.lower(), set()).add(verdict.lower())
    if "pass" in verdicts.get("dmarc", ()):
        return False
    if "fail" in verdicts.get("dmarc", ()):
        return True
    return verdicts.get("spf") == {"fail"} and verdicts.get("dkim") == {"fail"}


def _really_sent(source: SourceRecord) -> bool:
    """Mail the user sent sits in their Sent folder. A message that merely claims the
    user's address in From, delivered to the inbox, proves nothing about who they know."""
    labels = set(source.provider_labels)
    return "SENT" in labels or not labels


def canonical_addresses(
    people: Sequence[ResolvedIdentity], confirmed_aliases: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Which addresses may speak for the same person when deciding who can update a fact.

    Only links the user made by hand count. An *inferred* link (a compatible display name
    plus a self-identifying signature) is good enough to suggest "this might be Priya's
    other address", but anyone can write that signature, so it never lets a new address
    replace what the known one said.
    """
    return dict(confirmed_aliases or {})


def provenance(source: SourceRecord, user: Party, canonical: dict[str, str]) -> dict[str, Any]:
    def key(party: Party) -> str:
        address = party.address.lower()
        return canonical.get(address, address)

    sender = source.sender
    everyone = (*source.recipients, *([sender] if sender else []))
    return {
        "thread_id": source.thread_id,
        "sender_address": key(sender) if sender else None,
        "participants": frozenset(key(p) for p in everyone),
        # The user's own mail and notes. Not calendar entries: the connector files every event
        # under the calendar's owner, including invitations other people sent.
        "from_user": source.kind is SourceKind.USER_CAPTURE
        or (source.kind is SourceKind.EMAIL and is_from_user(source, user)),
    }


def run_pipeline(
    sources: Sequence[SourceRecord],
    user: Party,
    triager: Triager,
    extractor: Extractor,
    confirmed_aliases: Mapping[str, str] | None = None,
) -> PipelineResult:
    ordered = sorted(sources, key=lambda s: (s.observed_at, s.id))
    people = resolve_people(ordered, user)
    canonical = canonical_addresses(people, confirmed_aliases)
    # Someone the user has written to, as of each message. Merely having emailed the user
    # does not make a sender known.
    known_addresses: set[str] = set()
    silenced = silenced_calendar_versions(ordered)
    thread_history: dict[str, list[str]] = {}
    outcomes: list[SourceOutcome] = []
    drafts: list[DraftAssertion] = []

    for source in ordered:
        # Writing to someone is the proof of a relationship. A calendar invite is not: anyone
        # can send one, and it would promote its sender to "known".
        if source.kind is SourceKind.EMAIL and is_from_user(source, user) and _really_sent(source):
            known_addresses |= {p.address.lower() for p in source.recipients}
        decision = route(source, user)
        outcome = SourceOutcome(source_id=source.id, route=decision)
        outcomes.append(outcome)
        text = visible_text(source)
        candidates: tuple[Candidate, ...] = ()

        try:
            if decision is Route.STRUCTURED:
                event = None if source.id in silenced else calendar_candidate(source)
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
        except (ValueError, ArithmeticError) as problem:
            # One malformed or hostile message must never stop the rest of the user's mail:
            # bad values, impossible dates, numbers out of range. (Provider failures are a
            # different family of exception: they propagate, and the job retries.)
            outcome.failed = type(problem).__name__
            candidates = ()
        if source.kind is SourceKind.USER_CAPTURE and source.body.strip():
            # Whatever else is understood from it, what the user asked to remember is kept.
            candidates += (memory_candidate(source),)
        if source.thread_id and decision is not Route.SKIP:
            thread_history.setdefault(source.thread_id, []).append(text)

        sender = source.sender
        outcome.suspicious = (
            outcome.suspicious
            or looks_like_injection(source.body)
            or (sender is not None and is_user_lookalike(sender, user))
            or failed_sender_authentication(source)
        )
        structured = decision is Route.STRUCTURED
        for candidate in candidates:
            if not acceptable(candidate, source, text, outcome):
                continue
            by_code = structured or candidate.kind is CandidateKind.MEMORY
            method = "calendar" if structured else "capture" if by_code else extractor.method
            drafts.append(
                DraftAssertion(
                    candidate=candidate,
                    observed_at=source.observed_at,
                    **provenance(source, user, canonical),
                    extraction_method=method,
                    prompt_version="structured-v1" if by_code else extractor.prompt_version,
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
