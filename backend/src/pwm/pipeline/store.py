"""Persistence around the pure funnel: idempotent ingestion, cached model stages, and
writing the reconciled world. Nothing here ever writes `Assertion.review`."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
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
from pwm.pipeline.core import PipelineResult, run_pipeline
from pwm.sources import Party, SourceRecord

TRIAGE_VERSION = "triage-v1"


def ensure_user(session: Session, party: Party) -> User:
    user = session.scalar(select(User).where(User.email == party.address.lower()))
    if user is None:
        user = User(email=party.address.lower(), name=party.name)
        session.add(user)
        session.flush()
    return user


def ingest(session: Session, user: User, records: Sequence[SourceRecord]) -> int:
    """Store new source records and queue processing. Safe to call repeatedly with the same data."""
    inserted = 0
    for record in records:
        statement = (
            insert(Source)
            .values(
                user_id=user.id,
                external_id=record.id,
                kind=record.kind.value,
                thread_id=record.thread_id,
                observed_at=record.observed_at,
                record=record.model_dump(mode="json"),
            )  # fmt: skip
            .on_conflict_do_nothing(index_elements=["user_id", "external_id"])
        )
        inserted += len(session.execute(statement.returning(Source.id)).all())
    if inserted:
        newest = max(r.observed_at for r in records).isoformat()
        session.execute(
            insert(Job)
            .values(user_id=user.id, kind="process_user", key=f"{user.id}:{len(records)}:{newest}")
            .on_conflict_do_nothing(index_elements=["kind", "key"])
        )
    return inserted


class _StageCache:
    def __init__(self, session: Session, user: User, source_ids: dict[str, UUID]) -> None:
        self._session, self._user, self._source_ids = session, user, source_ids

    def load(self, external_id: str, stage: str, version: str) -> dict[str, object] | None:
        row = self._session.scalar(
            select(StageResult).where(
                StageResult.source_id == self._source_ids[external_id],
                StageResult.stage == stage,
                StageResult.version == version,
            )
        )
        return row.result if row else None

    def save(
        self, external_id: str, stage: str, version: str, result: dict[str, object],
        usage: Sequence[ModelUsage],
    ) -> None:  # fmt: skip
        source_id = self._source_ids[external_id]
        self._session.add(
            StageResult(
                user_id=self._user.id,
                source_id=source_id,
                stage=stage,
                version=version,
                result=result,
            )
        )
        for call in usage:
            self._session.add(
                ModelCall(user_id=self._user.id, source_id=source_id, **call.model_dump())
            )


class CachedTriager:
    def __init__(self, inner: Triager, cache: _StageCache) -> None:
        self._inner, self._cache = inner, cache

    def is_relevant(self, request: ExtractionRequest) -> TriageResult:
        if (stored := self._cache.load(request.source.id, "triage", TRIAGE_VERSION)) is not None:
            return TriageResult(relevant=bool(stored["relevant"]))
        result = self._inner.is_relevant(request)
        self._cache.save(
            request.source.id, "triage", TRIAGE_VERSION, {"relevant": result.relevant}, result.usage
        )
        return result


class CachedExtractor:
    def __init__(self, inner: Extractor, cache: _StageCache) -> None:
        self._inner, self._cache = inner, cache
        self.method, self.prompt_version = inner.method, inner.prompt_version

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        stored = self._cache.load(request.source.id, "extraction", self.prompt_version)
        if stored is not None:
            return ExtractionResult.model_validate(stored)
        result = self._inner.extract(request)
        self._cache.save(
            request.source.id, "extraction", self.prompt_version,
            result.model_dump(mode="json", exclude={"usage"}), result.usage,
        )  # fmt: skip
        return result


def _write_people(session: Session, user: User, result: PipelineResult) -> None:
    existing = {
        i.value: i
        for i in session.scalars(
            select(PersonIdentifier).where(PersonIdentifier.user_id == user.id)
        )
    }
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


def _write_assertions(
    session: Session, user: User, result: PipelineResult, source_ids: dict[str, UUID]
) -> int:
    rows: list[Assertion] = []
    created = 0
    for draft in result.assertions:
        c = draft.candidate
        method, version = draft.extraction_method, draft.prompt_version
        row = session.scalar(
            select(Assertion).where(
                Assertion.source_id == source_ids[c.source_id],
                Assertion.kind == c.kind.value,
                Assertion.evidence_quote == c.evidence_quote,
                Assertion.extraction_method == method,
                Assertion.prompt_version == version,
            )  # fmt: skip
        )
        if row is None:
            created += 1
            row = Assertion(
                user_id=user.id, source_id=source_ids[c.source_id], kind=c.kind.value,
                subject=c.subject, predicate=c.predicate, value=c.value,
                evidence_quote=c.evidence_quote, extraction_method=method, prompt_version=version,
                origin=c.origin.value, confidence=draft.confidence.value,
                # The user's own words need no second confirmation; nothing else starts confirmed.
                review="confirmed" if c.origin.value == "user_stated" else "unreviewed",
                valid_from=c.valid_from, valid_to=c.valid_to, observed_at=draft.observed_at,
                commitment_type=c.commitment_type.value if c.commitment_type else None,
                direction=c.direction.value if c.direction else None,
                committed_by=c.committed_by, committed_to=c.committed_to, due=c.due,
                status="open" if c.kind.value == "commitment" else None,
            )  # fmt: skip
            session.add(row)
        rows.append(row)
    session.flush()

    for draft, row in zip(result.assertions, rows, strict=True):
        # A user correction already points somewhere; code does not redirect it.
        if draft.superseded_by is not None and row.superseded_by_id is None:
            row.superseded_by_id = rows[draft.superseded_by].id
    for relation in result.relations:
        session.execute(
            insert(AssertionRelation)
            .values(
                user_id=user.id,
                type=relation.type.value,
                from_id=rows[relation.from_index].id,
                to_id=rows[relation.to_index].id,
            )  # fmt: skip
            .on_conflict_do_nothing(index_elements=["type", "from_id", "to_id"])
        )
    return created


def process_user(session: Session, user: User, triager: Triager, extractor: Extractor) -> int:
    """Run the funnel over everything the user has and store the result. Idempotent."""
    sources = list(session.scalars(select(Source).where(Source.user_id == user.id)))
    source_ids = {s.external_id: s.id for s in sources}
    records = [SourceRecord.model_validate(s.record) for s in sources]
    cache = _StageCache(session, user, source_ids)
    result = run_pipeline(
        records, Party(name=user.name, address=user.email),
        CachedTriager(triager, cache), CachedExtractor(extractor, cache),
    )  # fmt: skip
    by_external = {s.external_id: s for s in sources}
    for outcome in result.outcomes:
        source = by_external[outcome.source_id]
        source.route, source.suspicious = outcome.route.value, outcome.suspicious
        source.processed_with = extractor.prompt_version
    _write_people(session, user, result)
    return _write_assertions(session, user, result, source_ids)
