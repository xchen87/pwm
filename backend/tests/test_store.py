from datetime import UTC, datetime

import pytest
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


class Versioned(HeuristicExtractor):
    """Returns whatever candidates it is given, under a chosen method name."""

    def __init__(self, method: str, make: object) -> None:
        self.method, self._make = method, make

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        return ExtractionResult(candidates=tuple(self._make(request)))  # type: ignore[operator]


def _commitment(request: ExtractionRequest, quote: str, value: str, due: str | None = None):  # type: ignore[no-untyped-def]
    from datetime import date

    from pwm.extraction.candidates import (
        Candidate,
        CandidateKind,
        CommitmentType,
        Direction,
        Origin,
    )

    return Candidate(
        source_id=request.source.id, kind=CandidateKind.COMMITMENT, subject="Alex", predicate="committed_to",
        value=value, evidence_quote=quote, origin=Origin.SOURCE_EXPLICIT, commitment_type=CommitmentType.PROMISE,
        direction=Direction.BY_USER, due=date.fromisoformat(due) if due else None,
    )  # fmt: skip


def _one_mail(session: Session, user: User, body: str) -> None:
    from pwm.sources import Party, SourceKind, SourceRecord

    record = SourceRecord(
        id="only", kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, 1, tzinfo=UTC), thread_id="t",
        sender=Party(name=user.name, address=user.email), recipients=(Party(name="Tom", address="tom@x.example"),),
        subject="report", body=body,
    )  # fmt: skip
    ingest(session, user, [record])


def _rows(session: Session) -> list[Assertion]:
    return list(session.scalars(select(Assertion).order_by(Assertion.ordinal)))


def test_reprocessing_refreshes_unreviewed_rows_with_the_current_rules(
    session: Session, user: User
) -> None:
    _one_mail(session, user, "I will send the report by Friday.")
    quote = "I will send the report by Friday."
    v1 = Versioned("v1", lambda r: [_commitment(r, quote, "send the report", "2026-09-04")])
    v2 = Versioned("v2", lambda r: [_commitment(r, quote, "send the report", "2026-09-11")])
    process_user(session, user, HeuristicTriager(), v1)
    process_user(session, user, HeuristicTriager(), v2)
    (row,) = _rows(session)
    assert (row.due.isoformat(), row.extraction_method) == ("2026-09-11", "v2")  # type: ignore[union-attr]


def test_a_confirmed_fact_is_not_duplicated_when_a_new_model_rephrases_the_quote(
    session: Session, user: User
) -> None:
    _one_mail(session, user, "I will send the report by Friday.")
    v1 = Versioned(
        "v1", lambda r: [_commitment(r, "I will send the report by Friday.", "send the report")]
    )
    v2 = Versioned(
        "v2", lambda r: [_commitment(r, "I will send the report by Friday", "send the report")]
    )
    process_user(session, user, HeuristicTriager(), v1)
    review.confirm(session, user, _rows(session)[0].id)
    process_user(session, user, HeuristicTriager(), v2)
    assert [(r.review, r.extraction_method) for r in _rows(session)] == [("confirmed", "v1")]


def test_a_surviving_fact_is_not_mistaken_for_its_dismissed_sibling(
    session: Session, user: User
) -> None:
    body = "I'll send the report and book the venue."
    _one_mail(session, user, body)
    both = Versioned(
        "v1",
        lambda r: [_commitment(r, body, "send the report"), _commitment(r, body, "book the venue")],
    )
    only_venue = Versioned("v2", lambda r: [_commitment(r, body, "book the venue")])
    process_user(session, user, HeuristicTriager(), both)
    report = next(r for r in _rows(session) if r.value == "send the report")
    review.dismiss(session, user, report.id)
    process_user(session, user, HeuristicTriager(), only_venue)
    assert {(r.value, r.review) for r in _rows(session)} == {
        ("send the report", "rejected"), ("book the venue", "unreviewed"),
    }  # fmt: skip


def test_dismissing_a_wrong_update_brings_the_original_back(session: Session, user: User) -> None:
    from pwm.sources import Party, SourceKind, SourceRecord

    bob = Party(name="Bob", address="bob@x.example")
    mails = [
        SourceRecord(id=f"m{n}", kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, n, tzinfo=UTC),
                     thread_id="t", sender=bob, recipients=(Party(name=user.name, address=user.email),),
                     subject="quote", body=body)
        for n, body in ((1, "Our quote is $500 for the job."), (2, "Sorry, the total is $5,000 for the job."))
    ]  # fmt: skip
    ingest(session, user, mails)
    process_user(session, user, HeuristicTriager(), HeuristicExtractor())
    original = session.scalars(select(Assertion).where(Assertion.value == "500")).one()
    update = session.scalars(select(Assertion).where(Assertion.value == "5000")).one()
    assert original.superseded_by_id == update.id

    review.dismiss(session, user, update.id)
    process_user(session, user, HeuristicTriager(), HeuristicExtractor())
    session.refresh(original)
    assert original.superseded_by_id is None


def test_forgetting_a_note_also_removes_it_from_stored_briefs(
    session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PWM_FIXED_NOW", "2026-09-12T09:00:00+00:00")
    from pwm.brief import service
    from pwm.brief.writer import TemplateBriefWriter
    from pwm.db.models import Brief

    stages = (HeuristicTriager(), HeuristicExtractor())
    memory = review.remember(
        session, user, "My zebrafish licence ZX1234567: renew it by September 18.", *stages
    )
    derived = session.scalars(select(Assertion).where(Assertion.kind == "commitment")).one()
    review.confirm(session, user, derived.id)
    brief = service.generate(
        session, user, TemplateBriefWriter(), service.InboxNotifier(), "weekly"
    )
    assert "ZX1234567" in str(brief.items)

    review.forget(session, user, memory.id, *stages)
    assert all("ZX1234567" not in str(b.items) for b in session.scalars(select(Brief)))


def test_notes_are_the_users_words_whatever_characters_they_start_with(
    session: Session, user: User
) -> None:
    stages = (HeuristicTriager(), HeuristicExtractor())
    for text in ("> quoted line\nmy note about it", "<span hidden>secret</span> plan", "x" * 1800):
        memory = review.remember(session, user, text, *stages)
        assert memory.value == text and memory.review == "confirmed"


def _priced_thread(session: Session, user: User, bodies: list[str]) -> None:
    from pwm.sources import Party, SourceKind, SourceRecord

    bob = Party(name="Bob", address="bob@x.example")
    ingest(
        session, user,
        [
            SourceRecord(id=f"p{n}", kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, n + 1, tzinfo=UTC),
                         thread_id="t", sender=bob, recipients=(Party(name=user.name, address=user.email),),
                         subject="quote", body=body)
            for n, body in enumerate(bodies)
        ],
    )  # fmt: skip


def _value(session: Session, value: str) -> Assertion:
    return session.scalars(select(Assertion).where(Assertion.value == value)).one()


def test_a_dismissed_update_does_not_break_the_chain_to_a_later_genuine_one(
    session: Session, user: User
) -> None:
    _priced_thread(
        session,
        user,
        [
            "Our quote is $20 for it.",
            "Sorry, the total is $25 for it.",
            "Final: the total is $30 for it.",
        ],
    )
    stages = (HeuristicTriager(), HeuristicExtractor())
    process_user(session, user, *stages)
    review.dismiss(session, user, _value(session, "25").id)
    process_user(session, user, *stages)
    assert _value(session, "20").superseded_by_id == _value(session, "30").id
    assert _value(session, "30").superseded_by_id is None


def test_a_confirmed_fact_stays_replaced_even_when_a_run_no_longer_produces_it(
    session: Session, user: User
) -> None:
    from pwm.sources import Party, SourceKind, SourceRecord

    stages = (HeuristicTriager(), HeuristicExtractor())
    _priced_thread(session, user, ["Our quote is $20 for it."])
    process_user(session, user, *stages)
    old = _value(session, "20")
    review.confirm(session, user, old.id)

    update = SourceRecord(
        id="p1", kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, 5, tzinfo=UTC), thread_id="t",
        sender=Party(name="Bob", address="bob@x.example"),
        recipients=(Party(name=user.name, address=user.email),), subject="quote",
        body="Update: the total is $30 for it.",
    )  # fmt: skip
    ingest(session, user, [update])
    process_user(session, user, *stages)
    new = _value(session, "30")
    session.refresh(old)
    assert old.superseded_by_id == new.id

    class ForgetsTheFirstMail(HeuristicExtractor):
        method = "v2"

        def extract(self, request: ExtractionRequest) -> ExtractionResult:
            return ExtractionResult() if request.source.id == "p0" else super().extract(request)

    process_user(session, user, HeuristicTriager(), ForgetsTheFirstMail())
    session.refresh(old)
    assert (old.review, old.superseded_by_id) == ("confirmed", new.id)


def test_two_near_identical_candidates_cannot_make_a_fact_replace_itself(
    session: Session, user: User
) -> None:
    _one_mail(session, user, "The new price is $49 per month for all members.")
    quote = "The new price is $49 per month"
    v1 = Versioned("v1", lambda r: [_commitment(r, quote, "pay 49 per month")])
    process_user(session, user, HeuristicTriager(), v1)
    review.confirm(session, user, _rows(session)[0].id)
    v2 = Versioned("v2", lambda r: [_commitment(r, quote, "pay 49 per month", "2026-10-01"),
                                    _commitment(r, quote + " for all members", "pay 49 per month", "2026-11-01")])  # fmt: skip
    process_user(session, user, HeuristicTriager(), v2)
    for row in _rows(session):
        assert row.superseded_by_id != row.id


def test_a_different_fact_in_the_same_sentence_is_not_lost_to_a_dismissed_one(
    session: Session, user: User
) -> None:
    from pwm.extraction.candidates import Candidate, CandidateKind, Origin

    body = "Your plan renews on October 3 and the new price is $49 per month."
    _one_mail(session, user, body)

    def fact(request: ExtractionRequest, predicate: str, value: str) -> Candidate:
        return Candidate(source_id=request.source.id, kind=CandidateKind.THING, subject="Plan", predicate=predicate,
                         value=value, evidence_quote=body, origin=Origin.SOURCE_EXPLICIT)  # fmt: skip

    process_user(
        session,
        user,
        HeuristicTriager(),
        Versioned("v1", lambda r: [fact(r, "renews", "2026-10-03")]),
    )
    review.dismiss(session, user, _rows(session)[0].id)
    process_user(
        session,
        user,
        HeuristicTriager(),
        Versioned("v2", lambda r: [fact(r, "monthly_price", "49")]),
    )
    assert {(r.predicate, r.review) for r in _rows(session)} == {
        ("renews", "rejected"),
        ("monthly_price", "unreviewed"),
    }


def test_a_rephrased_quote_keeps_the_row_so_stored_briefs_survive(
    session: Session, user: User
) -> None:
    _one_mail(session, user, "I will send the report by Friday.")
    v1 = Versioned(
        "v1", lambda r: [_commitment(r, "I will send the report by Friday.", "send the report")]
    )
    v2 = Versioned(
        "v2", lambda r: [_commitment(r, "I will send the report by Friday", "send the report")]
    )
    process_user(session, user, HeuristicTriager(), v1)
    before = _rows(session)[0].id
    process_user(session, user, HeuristicTriager(), v2)
    (row,) = _rows(session)
    assert row.id == before and row.evidence_quote == "I will send the report by Friday"


def test_confirming_a_genuine_link_does_not_bless_an_impersonators_guessed_one(
    session: Session, user: User
) -> None:
    from pwm.db.models import Person
    from pwm.pipeline.store import _confirmed_aliases

    person = Person(user_id=user.id, display_name="Priya Raman")
    session.add(person)
    session.flush()
    for address, link in (
        ("priya@work.example", "exact"),
        ("priya.raman@evil.example", "inferred"),
        ("priya@home.example", "user"),
    ):
        session.add(
            PersonIdentifier(user_id=user.id, person_id=person.id, value=address, link=link)
        )
    session.flush()
    aliases = _confirmed_aliases(session, user)
    assert set(aliases) == {"priya@work.example", "priya@home.example"}
    assert len(set(aliases.values())) == 1


def test_a_hostile_sender_name_cannot_wedge_the_people_tables(session: Session, user: User) -> None:
    from pwm.sources import Party, SourceKind, SourceRecord

    me = Party(name=user.name, address=user.email)
    hostile = SourceRecord(
        id="h", kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, 1, tzinfo=UTC), thread_id="t",
        sender=Party(name="E" * 250 + " Smith", address="eve@x.example"), recipients=(me,),
        subject="hi", body="I'll send the file by Friday.",
    )  # fmt: skip
    ingest(session, user, [hostile])
    process_user(session, user, HeuristicTriager(), HeuristicExtractor())
    assert count(session, Assertion) >= 1


def test_the_address_that_joins_an_existing_person_is_always_a_guess(
    session: Session, world: User
) -> None:
    links = dict(session.execute(select(PersonIdentifier.value, PersonIdentifier.link)).all())  # type: ignore[arg-type]
    assert links["priya.n@example.com"] == "exact"
    assert links["priya@natarajan-design.example"] == "inferred"
    per_person = {}
    for identifier in session.scalars(select(PersonIdentifier)):
        per_person.setdefault(identifier.person_id, []).append(identifier.link)
    assert all(found.count("exact") == 1 for found in per_person.values())


def test_merging_people_does_not_vouch_for_their_guessed_addresses(
    session: Session, user: User
) -> None:
    from pwm.db.models import Person

    keep, absorbed = (
        Person(user_id=user.id, display_name="Priya"),
        Person(user_id=user.id, display_name="P. Raman"),
    )
    session.add_all([keep, absorbed])
    session.flush()
    for person, address, link in ((keep, "p@work.example", "exact"), (absorbed, "p@home.example", "exact"),
                                  (absorbed, "p@evil.example", "inferred")):  # fmt: skip
        session.add(
            PersonIdentifier(user_id=user.id, person_id=person.id, value=address, link=link)
        )
    session.flush()
    review.merge_people(session, user, keep.id, absorbed.id)
    links = dict(session.execute(select(PersonIdentifier.value, PersonIdentifier.link)).all())  # type: ignore[arg-type]
    assert links == {
        "p@work.example": "exact",
        "p@home.example": "user",
        "p@evil.example": "inferred",
    }


def test_dismissing_a_replacement_frees_the_original_at_once(session: Session, user: User) -> None:
    _priced_thread(session, user, ["Our quote is $20 for it.", "Update: the total is $30 for it."])
    process_user(session, user, HeuristicTriager(), HeuristicExtractor())
    old, new = _value(session, "20"), _value(session, "30")
    assert old.superseded_by_id == new.id
    review.dismiss(session, user, new.id)  # no pipeline run in between
    session.refresh(old)
    assert old.superseded_by_id is None


def test_a_dismissed_fact_stays_dismissed_when_a_new_extractor_rewords_everything(
    session: Session, user: User
) -> None:
    from pwm.extraction.candidates import Candidate, CandidateKind, Origin
    from pwm.pipeline.store import same_value

    assert same_value("$1450", "1450 USD monthly") and not same_value("2026-10-03", "49")
    body = (
        "The new price: the rent is $1450 from October."  # "price" gets it past rule-based triage
    )
    _one_mail(session, user, body)

    def fact(request: ExtractionRequest, predicate: str, value: str) -> Candidate:
        return Candidate(source_id=request.source.id, kind=CandidateKind.THING, subject="Flat", predicate=predicate,
                         value=value, evidence_quote=body, origin=Origin.SOURCE_EXPLICIT)  # fmt: skip

    process_user(
        session, user, HeuristicTriager(), Versioned("v1", lambda r: [fact(r, "price", "$1450")])
    )
    review.dismiss(session, user, _rows(session)[0].id)
    process_user(
        session,
        user,
        HeuristicTriager(),
        Versioned("v2", lambda r: [fact(r, "rent", "1450 USD monthly")]),
    )
    assert [(r.predicate, r.review) for r in _rows(session)] == [("price", "rejected")]
