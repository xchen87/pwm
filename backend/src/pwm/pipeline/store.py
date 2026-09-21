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

from pwm.db.models import (
    Assertion,
    AssertionRelation,
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
from pwm.sources import Party, SourceRecord

# A dismissed or corrected item must not come back because a new model phrased its quote
# slightly differently.
SAME_EVIDENCE = 0.6
USER_DECIDED = ("rejected", "corrected")


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


def _write_assertions(
    session: Session, user: User, result: PipelineResult, source_ids: dict[str, UUID]
) -> int:
    existing = list(session.scalars(select(Assertion).where(Assertion.user_id == user.id)))
    by_key = {(a.source_id, a.kind, a.quote_hash, a.ordinal): a for a in existing}
    decided = [a for a in existing if a.review in USER_DECIDED]

    rows: list[Assertion | None] = []
    seen: dict[tuple[UUID, str, str], int] = {}
    created = 0
    for draft in result.assertions:
        c = draft.candidate
        source_id, hashed = source_ids[c.source_id], quote_hash(c.evidence_quote)
        ordinal = seen.get((source_id, c.kind.value, hashed), 0)
        seen[(source_id, c.kind.value, hashed)] = ordinal + 1
        row = by_key.get((source_id, c.kind.value, hashed, ordinal))
        if row is None and any(
            d.source_id == source_id
            and d.kind == c.kind.value
            and similarity(d.evidence_quote, c.evidence_quote) >= SAME_EVIDENCE
            for d in decided
        ):
            rows.append(None)  # the user already ruled on this; a rephrased quote changes nothing
            continue
        if row is None:
            created += 1
            row = Assertion(
                user_id=user.id, source_id=source_id, kind=c.kind.value,
                subject=c.subject, predicate=c.predicate, value=c.value,
                evidence_quote=c.evidence_quote, quote_hash=hashed, ordinal=ordinal,
                extraction_method=draft.extraction_method, prompt_version=draft.prompt_version,
                origin=c.origin.value, confidence=draft.confidence.value, review="unreviewed",
                valid_from=c.valid_from, valid_to=c.valid_to, observed_at=draft.observed_at,
                commitment_type=c.commitment_type.value if c.commitment_type else None,
                direction=c.direction.value if c.direction else None,
                committed_by=c.committed_by, committed_to=c.committed_to, due=c.due,
                status="open" if c.kind.value == "commitment" else None,
            )  # fmt: skip
            session.add(row)
        rows.append(row)
    session.flush()

    # Machine-made assertions nobody has reviewed are disposable: if this run no longer
    # produces one (new extractor, new rules, deleted source), it goes. Anything the user
    # touched stays.
    current = {row.id for row in rows if row is not None}
    for stale in existing:
        if (
            stale.id not in current
            and stale.review == "unreviewed"
            and stale.extraction_method != "user_correction"
        ):
            session.delete(stale)
    session.flush()

    for draft, row in zip(result.assertions, rows, strict=True):
        if row is None or draft.superseded_by is None or row.superseded_by_id is not None:
            continue  # a user correction already points somewhere; code does not redirect it
        replacement = rows[draft.superseded_by]
        if replacement is not None:
            row.superseded_by_id = replacement.id
    session.execute(
        delete(AssertionRelation).where(
            AssertionRelation.user_id == user.id, AssertionRelation.made_by == "pipeline"
        )
    )
    for relation in result.relations:
        newer, older = rows[relation.from_index], rows[relation.to_index]
        if newer is not None and older is not None:
            session.add(
                AssertionRelation(
                    user_id=user.id,
                    type=relation.type.value,
                    from_id=newer.id,
                    to_id=older.id,
                    made_by="pipeline",
                )  # fmt: skip
            )
    return created


def process_user(
    session: Session, user: User, triager: Triager, extractor: Extractor,
    cache: StageCache | None = None,
) -> int:  # fmt: skip
    """Run the funnel over everything the user has and store the result. Idempotent."""
    # Two workers must not rebuild the same user's world at once.
    session.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(user.id)))))
    sources = list(session.scalars(select(Source).where(Source.user_id == user.id)))
    source_ids = {s.external_id: s.id for s in sources}
    records = [SourceRecord.model_validate(s.record) for s in sources]
    cache = cache or StageCache(session, user, source_ids)
    result = run_pipeline(
        records, Party(name=user.name, address=user.email),
        CachedTriager(triager, cache), CachedExtractor(extractor, cache),
    )  # fmt: skip
    by_external = {s.external_id: s for s in sources}
    for outcome in result.outcomes:
        source = by_external[outcome.source_id]
        source.route, source.suspicious = outcome.route.value, outcome.suspicious
        source.processed_with = f"{extractor.method}:{extractor.prompt_version}"[:64]
    _write_people(session, user, result)
    return _write_assertions(session, user, result, source_ids)


def stage_cache_for(session: Session, user: User) -> StageCache:
    sources = session.execute(
        select(Source.external_id, Source.id).where(Source.user_id == user.id)
    )
    return StageCache(session, user, {external: id_ for external, id_ in sources})


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
