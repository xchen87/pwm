from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pwm import review
from pwm.db.models import (
    Assertion,
    Job,
    ModelCall,
    Person,
    PersonIdentifier,
    ReviewEvent,
    Source,
    StageResult,
    User,
)
from pwm.extraction.interface import ExtractionRequest, ExtractionResult
from pwm.pipeline.heuristic import HeuristicExtractor, HeuristicTriager
from pwm.pipeline.store import ingest, process_user
from pwm.pipeline.worker import run_next
from pwm_eval.fixture import load_fixture

FIXTURE = load_fixture()


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


class CountingExtractor(HeuristicExtractor):
    calls = 0

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        self.calls += 1
        return super().extract(request)


def test_ingesting_the_same_sources_twice_changes_nothing(session: Session, user: User) -> None:
    assert ingest(session, user, FIXTURE.sources) == len(FIXTURE.sources)
    assert ingest(session, user, FIXTURE.sources) == 0
    assert count(session, Source) == len(FIXTURE.sources)
    assert count(session, Job) == 1


def test_reprocessing_is_idempotent_and_never_repays_for_a_model_call(
    session: Session, user: User
) -> None:
    ingest(session, user, FIXTURE.sources)
    extractor = CountingExtractor()
    created = process_user(session, user, HeuristicTriager(), extractor)
    calls, assertions = extractor.calls, count(session, Assertion)
    assert created == assertions > 0

    assert process_user(session, user, HeuristicTriager(), extractor) == 0
    assert extractor.calls == calls
    assert count(session, Assertion) == assertions


def test_the_pipeline_confirms_nothing_except_the_users_own_words(
    session: Session, world: User
) -> None:
    confirmed = session.scalars(select(Assertion).where(Assertion.review != "unreviewed")).all()
    assert confirmed and all(a.origin == "user_stated" for a in confirmed)
    assert all(a.source.kind == "user_capture" for a in confirmed)


def test_every_stored_assertion_has_provenance(session: Session, world: User) -> None:
    for assertion in session.scalars(select(Assertion)):
        assert assertion.evidence_quote and assertion.extraction_method and assertion.prompt_version
        assert assertion.confidence in {"high", "medium", "low"}


def test_a_users_decision_survives_reprocessing(session: Session, world: User) -> None:
    target = session.scalars(select(Assertion).where(Assertion.review == "unreviewed")).first()
    assert target is not None
    review.confirm(session, world, target.id)
    session.commit()
    process_user(session, world, HeuristicTriager(), HeuristicExtractor())
    assert session.get_one(Assertion, target.id).review == "confirmed"


def test_deleting_a_source_removes_everything_derived_from_it(
    session: Session, world: User
) -> None:
    source = session.scalar(select(Source).where(Source.external_id == "e_q3_1"))
    assert source is not None
    assert session.scalar(select(func.count()).where(Assertion.source_id == source.id))
    session.delete(source)
    session.commit()
    assert not session.scalar(select(func.count()).where(Assertion.source_id == source.id))
    assert not session.scalar(select(func.count()).where(StageResult.source_id == source.id))


def test_deleting_a_user_leaves_nothing_behind(session: Session, world: User) -> None:
    review.confirm(session, world, session.scalars(select(Assertion.id)).first())  # type: ignore[arg-type]
    session.delete(world)
    session.commit()
    for model in (
        Source,
        Assertion,
        Person,
        PersonIdentifier,
        StageResult,
        ReviewEvent,
        ModelCall,
        Job,
    ):
        assert count(session, model) == 0, model.__tablename__


def test_a_correction_is_a_new_assertion_and_the_original_is_kept(
    session: Session, world: User
) -> None:
    original = session.scalars(select(Assertion).where(Assertion.kind == "commitment")).first()
    assert original is not None
    fixed = review.correct(session, world, original.id, value="send Tom the Q3 deck")
    assert (fixed.origin, fixed.review, fixed.value) == (
        "user_stated",
        "confirmed",
        "send Tom the Q3 deck",
    )
    assert fixed.evidence_quote == original.evidence_quote
    assert (original.review, original.superseded_by_id) == ("corrected", fixed.id)
    assert count(session, ReviewEvent) == 1


def test_merge_and_split_are_respected_by_later_processing(session: Session, world: User) -> None:
    identifier = session.scalar(
        select(PersonIdentifier).where(PersonIdentifier.value == "priya@natarajan-design.example")
    )
    assert identifier is not None and identifier.link == "inferred"
    priya_id = identifier.person_id
    split = review.split_identifier(session, world, identifier.id, "Someone else")
    session.commit()
    process_user(session, world, HeuristicTriager(), HeuristicExtractor())
    session.refresh(identifier)
    assert (identifier.person_id, identifier.link) == (split.id, "user")

    review.merge_people(session, world, priya_id, split.id)
    session.commit()
    session.refresh(identifier)
    assert identifier.person_id == priya_id


class BrokenExtractor(HeuristicExtractor):
    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        raise TimeoutError("provider timed out")


def test_a_failed_job_is_recorded_and_retried_later(session: Session, user: User) -> None:
    ingest(session, user, FIXTURE.sources)
    session.commit()
    assert run_next(session, HeuristicTriager(), BrokenExtractor())
    job = session.scalars(select(Job)).one()
    assert (job.status, job.attempts) == ("pending", 1)
    assert "provider timed out" in (job.last_error or "")
    assert job.run_after > datetime.now(UTC)
    assert count(session, Assertion) == 0
    # Not due yet, so nothing runs now.
    assert not run_next(session, HeuristicTriager(), HeuristicExtractor())
