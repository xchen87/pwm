"""Rule-based stand-ins for the model stages.

These exist so the whole pipeline runs, and can be evaluated, with no model provider
configured (AGENT.md: "build a local mock adapter and continue"). They are a floor to
beat, not the product: they only see first-person promises, dated deadlines, explicit
"we decided" statements, and announced phone numbers.
"""

import re
from datetime import date

from pwm.extraction.candidates import Candidate, CandidateKind, CommitmentType, Direction, Origin
from pwm.extraction.interface import ExtractionRequest, ExtractionResult, TriageResult
from pwm.extraction.quotes import normalize
from pwm.pipeline import dates
from pwm.pipeline.prefilter import is_from_user
from pwm.pipeline.text import looks_like_injection
from pwm.sources import SourceKind

_CUES = re.compile(
    r"\b(I['’]ll|I will|will do|we['’]ve decided|I['’]ve decided|we decided|due|deadline|closes|"
    r"let me know by|rescheduled|new number|renews?|price|return|appointment|booked|quote|"
    r"dinner|total is)\b",
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
_MONEY = r"\$([\d,]+(?:\.\d{2})?)"
_PRICE_CHANGE = re.compile(rf"from\s+{_MONEY}\s+to\s+{_MONEY}(\s+(?:per|a)\s+month|/month)?", re.I)
_PREMIUM = re.compile(rf"premium is {_MONEY}", re.I)
_QUOTED_PRICE = re.compile(rf"\b(?:our quote is|revised total is|the total is) {_MONEY}", re.I)
_RETURN_WINDOW = re.compile(r"\breturn (?:this item|it|the item)?\s*until\b", re.I)
_EVENT_WORDS = re.compile(r"\b(appointment|rescheduled|booked|dinner|reservation)\b", re.I)
_CLOCK = re.compile(r"\bat (\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_TOPIC_PREFIX = re.compile(r"^\s*((re|fwd?)\s*:\s*)+", re.I)
_STRUCTURED_DATA = re.compile(r"[{\[]\s*\"|\":\s")
# A full stop after a title ("Dr. Amari") does not end a sentence.
MAX_SENTENCE = 600
_SENTENCE_END = re.compile(r"(?<!\bDr\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bMrs\.)(?<!\bSt\.)(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    found: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        # Prose only: a JSON blob or a paragraph addressed to "the AI" is not the author talking.
        if _STRUCTURED_DATA.search(paragraph) or looks_like_injection(paragraph):
            continue
        found.extend(s for s in _SENTENCE_END.split(normalize(paragraph)) if s)
    return found


def _number(text: str) -> str:
    value = text.replace(",", "")
    return value[:-3] if value.endswith(".00") else value


def _moment(sentence: str, written_on: date) -> str | None:
    day = dates.resolve(sentence, written_on)
    if day is None:
        return None
    if clock := _CLOCK.search(sentence):
        hour = int(clock[1]) % 12 + (12 if clock[3].lower() == "pm" else 0)
        return f"{day.isoformat()}T{hour:02d}:{int(clock[2] or 0):02d}"
    return day.isoformat()


class HeuristicTriager:
    version = "heuristic-triage-v1"

    def is_relevant(self, request: ExtractionRequest) -> TriageResult:
        return TriageResult(relevant=bool(_CUES.search(request.visible_text)))


class HeuristicExtractor:
    method = "heuristic"
    prompt_version = "heuristic-v1"

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        source, user = request.source, request.user
        if source.sender is None:
            return ExtractionResult()
        author = (source.sender.name or source.sender.address)[:200]
        user_name = (user.name or user.address)[:200]
        by_user = is_from_user(source, user)
        from_capture = source.kind is SourceKind.USER_CAPTURE
        origin = Origin.USER_STATED if from_capture else Origin.SOURCE_EXPLICIT
        written_on = source.observed_at.date()
        others = [
            (p.name or p.address)[:200] for p in source.recipients if p.address != user.address
        ]
        found: list[Candidate] = []

        def commitment(quote: str, kind: CommitmentType, by: str, to: str | None) -> None:
            # A deadline is the user's to meet whoever announced it. A promise belongs to
            # whoever made it, judged by address: a display name proves nothing.
            mine = kind is CommitmentType.DEADLINE or by_user or from_capture
            direction = Direction.BY_USER if mine else Direction.TO_USER
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
            if len(sentence) > MAX_SENTENCE:
                continue  # evidence is a passage; a run-on this long is not one
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
            found.extend(self._facts(sentence, request, origin))
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

    def _facts(self, sentence: str, request: ExtractionRequest, origin: Origin) -> list[Candidate]:
        """Dated and priced facts. The subject is the thread's topic: crude, but stable within
        a thread, which is what lets a later message supersede an earlier one."""
        source = request.source
        written_on = source.observed_at.date()
        topic = (_TOPIC_PREFIX.sub("", source.subject).strip() or "Note")[:300]
        effective = dates.resolve(sentence, written_on) or dates.resolve(
            request.visible_text, written_on
        )

        def fact(
            kind: CandidateKind, predicate: str, value: str, **extra: date | None
        ) -> Candidate:
            return Candidate(
                source_id=source.id, kind=kind, subject=topic, predicate=predicate, value=value,
                evidence_quote=sentence, origin=origin, **extra,
            )  # fmt: skip

        facts: list[Candidate] = []
        if change := _PRICE_CHANGE.search(sentence):
            predicate = "monthly_rent" if "rent" in sentence.lower() else "monthly_price"
            facts.append(
                fact(CandidateKind.THING, predicate, _number(change[2]), valid_from=effective)
            )
        elif premium := _PREMIUM.search(sentence):
            facts.append(
                fact(
                    CandidateKind.THING, "annual_premium", _number(premium[1]), valid_from=effective
                )
            )
        elif quoted := _QUOTED_PRICE.search(sentence):
            facts.append(fact(CandidateKind.THING, "quote", _number(quoted[1])))
        if _RETURN_WINDOW.search(sentence) and (ends := dates.resolve(sentence, written_on)):
            facts.append(
                fact(CandidateKind.THING, "return_window_ends", ends.isoformat(), valid_to=ends)
            )
        if _EVENT_WORDS.search(sentence) and (moment := _moment(sentence, written_on)):
            facts.append(fact(CandidateKind.EVENT, "date", moment))
        return facts
