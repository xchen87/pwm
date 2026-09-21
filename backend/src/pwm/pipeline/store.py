"""Persistence around the pure funnel: idempotent ingestion, cached model stages, and
writing the reconciled world.

Nothing in this module writes `Assertion.review`: every assertion it creates starts
unreviewed, and only `pwm.review` (user actions) changes that.
"""

import hashlib
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pwm import clock
from pwm.db.models import (
    Assertion,
    AssertionRelation,
    Brief,
    Job,
    ModelCall,
    Person,
    PersonIdentifier,
    Source,
    StageResult,
    User,
)
from pwm.extraction.interface import (
    ExtractionRequest,
    ExtractionResult,
    Extractor,
    ModelUsage,
    Triager,
    TriageResult,
)
from pwm.extraction.quotes import normalize
from pwm.pipeline.core import PipelineResult, run_pipeline
from pwm.pipeline.text import similarity
from pwm.pipeline.world import DraftAssertion
from pwm.sources import Party, SourceRecord

# A dismissed or corrected item must not come back because a new model phrased its quote
# slightly differently.
SAME_EVIDENCE = 0.6


def quote_hash(quote: str) -> str:
    return hashlib.sha256(normalize(quote).encode()).hexdigest()


def ensure_user(session: Session, party: Party) -> User:
    user = session.scalar(select(User).where(User.email == party.address.lower()))
    if user is None:
        user = User(email=party.address.lower(), name=party.name)
        session.add(user)
        session.flush()
    return user


def ingest(
    session: Session, user: User, records: Sequence[SourceRecord], connector: str = "manual"
) -> int:
    """Store new source records and queue processing. Safe to call repeatedly with the same data."""
    inserted = 0
    for record in records:
        statement = (
            insert(Source)
            .values(
                user_id=user.id,
                external_id=record.id,
                connector=connector,
                kind=record.kind.value,
                thread_id=record.thread_id,
                observed_at=record.observed_at,
                record=record.model_dump(mode="json"),
            )  # fmt: skip
            .on_conflict_do_nothing(index_elements=["user_id", "external_id"])
            .returning(Source.id)
        )
        inserted += len(session.execute(statement).all())
    if inserted:
        enqueue(session, user)
    return inserted


def enqueue(session: Session, user: User) -> None:
    """One pending job per user is enough: a job processes everything the user has."""
    pending = session.scalar(
        select(func.count()).where(Job.user_id == user.id, Job.status == "pending")
    )
    if not pending:
        session.add(Job(user_id=user.id, kind="process_user", key=str(uuid4())))


class StageCache:
    """Stored model-stage results.

    Rows written during a run are remembered so that, if the run fails and is rolled
    back, `replay` can put them back: a call that was paid for is never paid for twice,
    and its audit row is never lost.
    """

    def __init__(self, session: Session, user: User, source_ids: dict[str, UUID]) -> None:
        self._session, self._user, self._source_ids = session, user, source_ids
        self._written: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []

    def load(self, external_id: str, stage: str, version: str) -> dict[str, Any] | None:
        row = self._session.scalar(
            select(StageResult).where(
                StageResult.source_id == self._source_ids[external_id],
                StageResult.stage == stage,
                StageResult.version == version,
            )
        )
        return row.result if row else None

    def save(
        self, external_id: str, stage: str, version: str, result: dict[str, Any] | None,
        usage: Sequence[ModelUsage],
    ) -> None:  # fmt: skip
        """`result=None` records the spend without caching the answer."""
        source_id = self._source_ids[external_id]
        stored = (
            {"user_id": self._user.id, "source_id": source_id, "stage": stage,
             "version": version, "result": result}
            if result is not None else {}
        )  # fmt: skip
        calls = [
            {"user_id": self._user.id, "source_id": source_id, **call.model_dump()}
            for call in usage
        ]
        self._written.append((stored, calls))
        self._add(stored, calls)

    def _add(self, stored: dict[str, Any], calls: list[dict[str, Any]]) -> None:
        if stored:
            self._session.add(StageResult(**stored))
        for call in calls:
            self._session.add(ModelCall(**call))

    def replay(self) -> None:
        for stored, calls in self._written:
            self._add(stored, calls)


class CachedTriager:
    def __init__(self, inner: Triager, cache: StageCache) -> None:
        self._inner, self._cache = inner, cache
        self.version = inner.version

    def is_relevant(self, request: ExtractionRequest) -> TriageResult:
        if (stored := self._cache.load(request.source.id, "triage", self.version)) is not None:
            return TriageResult(relevant=bool(stored["relevant"]))
        result = self._inner.is_relevant(request)
        answer = {"relevant": result.relevant} if result.cacheable else None
        self._cache.save(request.source.id, "triage", self.version, answer, result.usage)
        return result


class CachedExtractor:
    def __init__(self, inner: Extractor, cache: StageCache) -> None:
        self._inner, self._cache = inner, cache
        self.method, self.prompt_version = inner.method, inner.prompt_version
        # The method names the implementation and model, so answers from one model are
        # never reused, or relabelled, as another's.
        self._version = f"{inner.method}:{inner.prompt_version}"[:64]

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        stored = self._cache.load(request.source.id, "extraction", self._version)
        if stored is not None:
            return ExtractionResult.model_validate(stored)
        result = self._inner.extract(request)
        answer = result.model_dump(mode="json", exclude={"usage"}) if result.cacheable else None
        self._cache.save(request.source.id, "extraction", self._version, answer, result.usage)
        return result


def _write_people(session: Session, user: User, result: PipelineResult) -> None:
    existing = {
        i.value: i
        for i in session.scalars(
            select(PersonIdentifier).where(PersonIdentifier.user_id == user.id)
        )
    }
    derived = {address for identity in result.people for address in identity.addresses}
    for identity in result.people:
        # A link the user made or broke is never overridden by code.
        known = [existing[a] for a in identity.addresses if a in existing]
        person_id = known[0].person_id if known else None
        if person_id is None:
            person = Person(user_id=user.id, display_name=identity.name)
            session.add(person)
            session.flush()
            person_id = person.id
        for address in identity.addresses:
            if address in existing:
                continue
            link = "inferred" if address in identity.inferred_links else "exact"
            identifier = PersonIdentifier(
                user_id=user.id, person_id=person_id, value=address, link=link
            )
            session.add(identifier)
            existing[address] = identifier

    # People are derived data too: when the sources that mentioned someone are gone, so
    # are they. Identifiers the user placed by hand are kept.
    for address, identifier in existing.items():
        if address not in derived and identifier.link != "user":
            session.delete(identifier)
    session.flush()
    session.execute(
        delete(Person).where(
            Person.user_id == user.id,
            ~select(PersonIdentifier.id).where(PersonIdentifier.person_id == Person.id).exists(),
        )
    )


MUTABLE = (
    "subject", "predicate", "value", "valid_from", "valid_to", "commitment_type", "direction",
    "committed_by", "committed_to", "due",
)  # fmt: skip


def _fields(draft: DraftAssertion) -> dict[str, Any]:
    c = draft.candidate
    return {
        "subject": c.subject, "predicate": c.predicate, "value": c.value,
        "valid_from": c.valid_from, "valid_to": c.valid_to,
        "commitment_type": c.commitment_type.value if c.commitment_type else None,
        "direction": c.direction.value if c.direction else None,
        "committed_by": c.committed_by, "committed_to": c.committed_to, "due": c.due,
    }  # fmt: skip


def _pair_up(
    drafts: list[tuple[int, DraftAssertion]], siblings: list[Assertion]
) -> dict[int, Assertion]:
    """Match this run's candidates to stored rows that share their source, kind and quote.

    Usually there is one of each and they are the same fact, however differently two
    extractors phrase its value. When a sentence supports several facts, they are told
    apart by what they say, never by position: otherwise a fact that survives could be
    mistaken for a sibling the user dismissed.
    """
    if len(drafts) == 1 and len(siblings) == 1:
        return {drafts[0][0]: siblings[0]}
    scored = sorted(
        (
            (similarity(d.candidate.value, row.value), index, row)
            for index, d in drafts
            for row in siblings
        ),
        key=lambda item: -item[0],
    )  # fmt: skip
    paired: dict[int, Assertion] = {}
    taken: set[UUID] = set()
    for score, index, row in scored:
        if score >= SAME_EVIDENCE and index not in paired and row.id not in taken:
            paired[index] = row
            taken.add(row.id)
    return paired


def _write_assertions(
    session: Session, user: User, result: PipelineResult, source_ids: dict[str, UUID]
) -> int:
    existing = [
        a
        for a in session.scalars(select(Assertion).where(Assertion.user_id == user.id))
        if a.extraction_method != "user_correction"
    ]
    by_identity: dict[tuple[UUID, str, str], list[Assertion]] = {}
    for a in existing:
        by_identity.setdefault((a.source_id, a.kind, a.quote_hash), []).append(a)
    reviewed = [a for a in existing if a.review != "unreviewed"]

    grouped: dict[tuple[UUID, str, str], list[tuple[int, DraftAssertion]]] = {}
    for index, draft in enumerate(result.assertions):
        c = draft.candidate
        key = (source_ids[c.source_id], c.kind.value, quote_hash(c.evidence_quote))
        grouped.setdefault(key, []).append((index, draft))

    rows: list[Assertion | None] = [None] * len(result.assertions)
    settled: set[int] = set()
    created = 0
    for key, drafts in grouped.items():
        source_id, kind, hashed = key
        siblings = by_identity.get(key, [])
        paired = _pair_up(drafts, siblings)
        next_ordinal = max((a.ordinal for a in siblings), default=-1) + 1
        for index, draft in drafts:
            row = paired.get(index)
            quote = draft.candidate.evidence_quote
            if row is None:
                # The user may already have ruled on this under a slightly different quote
                # (a new model trims a full stop). Their ruling stands; no fresh copy appears.
                earlier = next(
                    (
                        r for r in reviewed
                        if r.source_id == source_id and r.kind == kind
                        and similarity(r.evidence_quote, quote) >= SAME_EVIDENCE
                        and similarity(r.value, draft.candidate.value) >= SAME_EVIDENCE
                    ),
                    None,
                )  # fmt: skip
                if earlier is not None:
                    rows[index] = earlier if earlier.review == "confirmed" else None
                    settled.add(index)
                    continue
                row = Assertion(
                    user_id=user.id, source_id=source_id, kind=kind,
                    evidence_quote=draft.candidate.evidence_quote, quote_hash=hashed,
                    ordinal=next_ordinal, review="unreviewed", observed_at=draft.observed_at,
                    recorded_at=clock.now(),
                    status="open" if kind == "commitment" else None,
                )  # fmt: skip
                next_ordinal += 1
                created += 1
                session.add(row)
            if row.review == "unreviewed":
                # Nobody has looked at this yet, so it always reflects the current rules,
                # extractor, and what is now known about the sender.
                for name, value in _fields(draft).items():
                    setattr(row, name, value)
                row.extraction_method, row.prompt_version = (
                    draft.extraction_method,
                    draft.prompt_version,
                )
                row.origin = draft.candidate.origin.value
            # Trust can change after the fact (a sender turns out to be suspicious).
            row.confidence = draft.confidence.value
            rows[index] = row if row.review in ("unreviewed", "confirmed") else None
    session.flush()

    # Machine-made assertions nobody has reviewed are disposable: if this run no longer
    # produces one (new extractor, new rules, deleted source), it goes. Anything the user
    # touched stays.
    current = {row.id for row in rows if row is not None}
    for stale in existing:
        if stale.id not in current and stale.review == "unreviewed":
            session.delete(stale)
    session.flush()

    # Supersession is recomputed every run, so dismissing a wrong "update" brings the
    # original back. Pointers to the user's own corrections are never touched.
    corrections = set(
        session.scalars(
            select(Assertion.id).where(
                Assertion.user_id == user.id, Assertion.extraction_method == "user_correction"
            )
        )
    )
    for row in existing:
        if row.superseded_by_id is not None and row.superseded_by_id not in corrections:
            row.superseded_by_id = None
    for draft, row in zip(result.assertions, rows, strict=True):
        if row is None or draft.superseded_by is None or row.superseded_by_id is not None:
            continue
        replacement = rows[draft.superseded_by]
        if replacement is not None:  # a rejected replacement replaces nothing
            row.superseded_by_id = replacement.id
    session.execute(
        delete(AssertionRelation).where(
            AssertionRelation.user_id == user.id, AssertionRelation.made_by == "pipeline"
        )
    )
    for relation in result.relations:
        newer, older = rows[relation.from_index], rows[relation.to_index]
        if newer is not None and older is not None and newer.id != older.id:
            session.execute(
                insert(AssertionRelation)
                .values(
                    user_id=user.id,
                    type=relation.type.value,
                    from_id=newer.id,
                    to_id=older.id,
                    made_by="pipeline",
                )  # fmt: skip
                .on_conflict_do_nothing(index_elements=["type", "from_id", "to_id"])
            )
    return created


def prune_briefs(session: Session, user: User) -> None:
    """Stored briefs quote evidence. When the assertion behind an item is gone (its source
    was deleted, or the user forgot a note), the item goes too; an emptied brief is removed."""
    alive = {
        str(i) for i in session.scalars(select(Assertion.id).where(Assertion.user_id == user.id))
    }
    for brief in session.scalars(select(Brief).where(Brief.user_id == user.id)):
        kept = [
            item for item in brief.items
            if item["item"]["assertion_id"] in alive
            and (item["item"].get("other_assertion_id") or item["item"]["assertion_id"]) in alive
        ]  # fmt: skip
        if not kept:
            session.delete(brief)
        elif len(kept) != len(brief.items):
            brief.items = kept


def process_user(
    session: Session, user: User, triager: Triager, extractor: Extractor,
    cache_sink: list[StageCache] | None = None,
) -> int:  # fmt: skip
    """Run the funnel over everything the user has and store the result. Idempotent.

    `cache_sink` receives the stage cache so a caller that rolls this run back can replay
    the model results that were paid for.
    """
    # Two workers must not rebuild the same user's world at once. Everything below,
    # including the list of sources, is read after the lock is held.
    session.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(user.id)))))
    sources = list(session.scalars(select(Source).where(Source.user_id == user.id)))
    source_ids = {s.external_id: s.id for s in sources}
    records = [SourceRecord.model_validate(s.record) for s in sources]
    cache = StageCache(session, user, source_ids)
    if cache_sink is not None:
        cache_sink.append(cache)
    # Only links the user made themselves let a second address speak for a person.
    confirmed_aliases = _confirmed_aliases(session, user)
    result = run_pipeline(
        records, Party(name=user.name, address=user.email),
        CachedTriager(triager, cache), CachedExtractor(extractor, cache),
        confirmed_aliases=confirmed_aliases,
    )  # fmt: skip
    by_external = {s.external_id: s for s in sources}
    for outcome in result.outcomes:
        source = by_external[outcome.source_id]
        source.route, source.suspicious = outcome.route.value, outcome.suspicious
        source.processed_with = f"{extractor.method}:{extractor.prompt_version}"[:64]
    _write_people(session, user, result)
    created = _write_assertions(session, user, result, source_ids)
    prune_briefs(session, user)
    return created


def _confirmed_aliases(session: Session, user: User) -> dict[str, str]:
    """address -> the person it belongs to, for identifiers the user linked by hand."""
    rows = session.execute(
        select(PersonIdentifier.value, PersonIdentifier.person_id).where(
            PersonIdentifier.user_id == user.id
        )
    ).all()
    by_person: dict[UUID, list[str]] = {}
    for address, person_id in rows:
        by_person.setdefault(person_id, []).append(address)
    user_linked = set(
        session.scalars(
            select(PersonIdentifier.person_id).where(
                PersonIdentifier.user_id == user.id, PersonIdentifier.link == "user"
            )
        )
    )
    return {
        address: sorted(addresses)[0]
        for person_id, addresses in by_person.items()
        if person_id in user_linked
        for address in addresses
    }


def delete_sources(
    session: Session,
    user: User,
    external_ids: Sequence[str],
    triager: Triager,
    extractor: Extractor,
) -> None:
    """Remove sources and everything derived from them, including people only they mentioned."""
    session.execute(
        delete(Source).where(Source.user_id == user.id, Source.external_id.in_(external_ids))
    )
    session.expire_all()
    process_user(session, user, triager, extractor)
