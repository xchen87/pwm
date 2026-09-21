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


def test_the_pipeline_confirms_nothing_at_all(session: Session, world: User) -> None:
    reviews = set(session.scalars(select(Assertion.review)))
    assert reviews == {"unreviewed"}
    assert count(session, ReviewEvent) == 0


def test_every_user_note_is_kept_verbatim_as_a_memory(session: Session, world: User) -> None:
    memories = session.scalars(select(Assertion).where(Assertion.kind == "memory")).all()
    assert {m.value for m in memories} >= {"Priya is my sister."}
    assert all(m.origin == "user_stated" and m.extraction_method == "capture" for m in memories)


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
    assert job.last_error == "TimeoutError"
    assert job.run_after > datetime.now(UTC)
    assert count(session, Assertion) == 0
    # Not due yet, so nothing runs now.
    assert not run_next(session, HeuristicTriager(), HeuristicExtractor())


class OtherModelExtractor(HeuristicExtractor):
    method = "anthropic:some-new-model"
    prompt_version = "extraction-v9"


def test_changing_the_extractor_meets_earlier_decisions_instead_of_duplicating(
    session: Session, world: User
) -> None:
    rows = session.scalars(select(Assertion).where(Assertion.kind == "commitment")).all()
    dismissed, confirmed = rows[0], rows[1]
    review.dismiss(session, world, dismissed.id)
    review.confirm(session, world, confirmed.id)
    before = count(session, Assertion)

    process_user(session, world, HeuristicTriager(), OtherModelExtractor())
    assert count(session, Assertion) == before
    assert session.get_one(Assertion, dismissed.id).review == "rejected"
    assert session.get_one(Assertion, confirmed.id).review == "confirmed"


class SilentExtractor(HeuristicExtractor):
    method = "silent"

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        return ExtractionResult()


def test_unreviewed_guesses_a_new_extractor_no_longer_makes_are_retired(
    session: Session, world: User
) -> None:
    kept = session.scalars(select(Assertion).where(Assertion.kind == "commitment")).first()
    assert kept is not None
    review.confirm(session, world, kept.id)
    process_user(session, world, HeuristicTriager(), SilentExtractor())
    remaining = session.scalars(select(Assertion).where(Assertion.kind == "commitment")).all()
    assert [a.id for a in remaining] == [kept.id]


def test_a_very_long_quote_is_rejected_before_it_can_break_storage() -> None:
    import pytest
    from pydantic import ValidationError

    from pwm.extraction.candidates import Candidate, CandidateKind, Origin

    with pytest.raises(ValidationError):
        Candidate(
            source_id="s", kind=CandidateKind.THING, subject="x", predicate="p", value="v",
            evidence_quote="word " * 5000, origin=Origin.SOURCE_EXPLICIT,
        )  # fmt: skip


def test_people_only_a_deleted_source_mentioned_are_removed_too(
    session: Session, world: User
) -> None:
    from pwm.pipeline.store import delete_sources

    addresses = lambda: set(session.scalars(select(PersonIdentifier.value)))  # noqa: E731
    assert "tokafor.home@example.com" in addresses()
    delete_sources(session, world, ["e_tom_home"], HeuristicTriager(), HeuristicExtractor())
    assert "tokafor.home@example.com" not in addresses()
    assert "tom.okafor@brightwave.example" in addresses()


def test_a_failed_run_keeps_what_was_already_paid_for(session: Session, user: User) -> None:
    class PaidThenBroken(HeuristicExtractor):
        calls = 0

        def extract(self, request: ExtractionRequest) -> ExtractionResult:
            self.calls += 1
            if self.calls > 5:
                raise TimeoutError("secret message text must not be stored")
            return super().extract(request)

    ingest(session, user, FIXTURE.sources)
    session.commit()
    run_next(session, HeuristicTriager(), PaidThenBroken())
    job = session.scalars(select(Job)).one()
    assert job.last_error == "TimeoutError"
    assert count(session, Assertion) == 0
    assert count(session, StageResult) >= 5


def test_new_mail_after_a_finished_job_is_always_queued(session: Session, user: User) -> None:
    ingest(session, user, FIXTURE.sources[:1])
    session.commit()
    run_next(session, HeuristicTriager(), HeuristicExtractor())
    same_time = FIXTURE.sources[1].model_copy(
        update={"observed_at": FIXTURE.sources[0].observed_at}
    )
    assert ingest(session, user, [same_time]) == 1
    session.commit()
    assert run_next(session, HeuristicTriager(), HeuristicExtractor())
