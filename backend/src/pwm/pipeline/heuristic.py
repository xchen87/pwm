"""Rule-based stand-ins for the model stages.

These exist so the whole pipeline runs, and can be evaluated, with no model provider
configured (AGENT.md: "build a local mock adapter and continue"). They are a floor to
beat, not the product: they only see first-person promises, dated deadlines, explicit
"we decided" statements, and announced phone numbers.
"""

import re

from pwm.extraction.candidates import Candidate, CandidateKind, CommitmentType, Direction, Origin
from pwm.extraction.interface import ExtractionRequest, ExtractionResult, TriageResult
from pwm.extraction.quotes import normalize
from pwm.pipeline import dates
from pwm.pipeline.prefilter import is_from_user
from pwm.pipeline.text import looks_like_injection
from pwm.sources import SourceKind

_CUES = re.compile(
    r"\b(I['’]ll|I will|will do|we['’]ve decided|I['’]ve decided|we decided|due|deadline|closes|"
    r"let me know by|rescheduled|new number|renews?|price|return)\b",
    re.I,
)
_PROMISE = re.compile(r"\b(I['’]ll|I will|I['’]m going to|will do)\b", re.I)
_HYPOTHETICAL = re.compile(
    r"^\s*if\b|\b(might|someday|sometime|I['’]d love|would love|we should|maybe)\b", re.I
)
_DEADLINE = re.compile(
    r"\b((is|are) due|closes|deadline is|let me know by|no later than|must be (received|in) by)\b",
    re.I,
)
_USER_DEADLINE = re.compile(
    r"\b(renew|pay|submit|file|register|send|return|book)\b.{0,40}\bby\b", re.I
)
_DECISION = re.compile(r"\b(we|I)(['’]ve| have)? decided\b", re.I)
_NEW_PHONE = re.compile(r"\bnew (?:number|phone)(?: number)? is ([\d][\d\-. ]{5,}\d)", re.I)
_STRUCTURED_DATA = re.compile(r"[{\[]\s*\"|\":\s")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    found: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        # Prose only: a JSON blob or a paragraph addressed to "the AI" is not the author talking.
        if _STRUCTURED_DATA.search(paragraph) or looks_like_injection(paragraph):
            continue
        found.extend(s for s in _SENTENCE_END.split(normalize(paragraph)) if s)
    return found


class HeuristicTriager:
    def is_relevant(self, request: ExtractionRequest) -> TriageResult:
        return TriageResult(relevant=bool(_CUES.search(request.visible_text)))


class HeuristicExtractor:
    method = "heuristic"
    prompt_version = "heuristic-v1"

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        source, user = request.source, request.user
        if source.sender is None:
            return ExtractionResult()
        author = source.sender.name or source.sender.address
        user_name = user.name or user.address
        by_user = is_from_user(source, user)
        from_capture = source.kind is SourceKind.USER_CAPTURE
        origin = Origin.USER_STATED if from_capture else Origin.SOURCE_EXPLICIT
        written_on = source.observed_at.date()
        others = [p.name or p.address for p in source.recipients if p.address != user.address]
        found: list[Candidate] = []

        def commitment(quote: str, kind: CommitmentType, by: str, to: str | None) -> None:
            direction = Direction.BY_USER if by == user_name else Direction.TO_USER
            found.append(
                Candidate(
                    source_id=source.id,
                    kind=CandidateKind.COMMITMENT,
                    subject=by,
                    predicate="deadline" if kind is CommitmentType.DEADLINE else "committed_to",
                    value=quote,
                    evidence_quote=quote,
                    origin=origin,
                    commitment_type=kind,
                    direction=direction,
                    committed_by=by,
                    committed_to=to,
                    due=dates.resolve(quote, written_on),
                )  # fmt: skip
            )

        for sentence in sentences(request.visible_text):
            if _DECISION.search(sentence) and (by_user or from_capture or "we" in sentence.lower()):
                found.append(
                    Candidate(
                        source_id=source.id,
                        kind=CandidateKind.DECISION,
                        subject=source.subject,
                        predicate="decided",
                        value=sentence,
                        evidence_quote=sentence,
                        origin=origin,
                    )  # fmt: skip
                )
            elif _DEADLINE.search(sentence) and dates.resolve(sentence, written_on):
                commitment(sentence, CommitmentType.DEADLINE, user_name, None)
            elif (
                from_capture
                and _USER_DEADLINE.search(sentence)
                and dates.resolve(sentence, written_on)
            ):
                commitment(sentence, CommitmentType.DEADLINE, user_name, None)
            elif _PROMISE.search(sentence) and not _HYPOTHETICAL.search(sentence):
                to = (others[0] if others else None) if by_user else user_name
                commitment(sentence, CommitmentType.PROMISE, author, to)
            if phone := _NEW_PHONE.search(sentence):
                found.append(
                    Candidate(
                        source_id=source.id,
                        kind=CandidateKind.PERSON,
                        subject=author,
                        predicate="phone",
                        value=phone[1],
                        evidence_quote=phone[0],
                        origin=origin,
                    )  # fmt: skip
                )
        return ExtractionResult(
            candidates=tuple(found), suspicious_content=looks_like_injection(request.visible_text)
        )
