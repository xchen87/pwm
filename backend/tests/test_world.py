"""Stages 7-8 tested on the gold assertions, so extractor quality is not a factor."""

from pwm.extraction.candidates import Candidate, CandidateKind, Origin
from pwm.pipeline.core import canonical_addresses, provenance
from pwm.pipeline.resolution import resolve_people
from pwm.pipeline.world import Confidence, DraftAssertion, as_of, assign_confidence, reconcile
from pwm_eval.fixture import load_fixture

FIXTURE = load_fixture()
GOLD = FIXTURE.gold


def gold_drafts() -> list[DraftAssertion]:
    canonical = canonical_addresses(resolve_people(FIXTURE.sources, GOLD.user))
    drafts = []
    for assertion in GOLD.assertions:
        source = FIXTURE.source(assertion.source_id)
        drafts.append(
            DraftAssertion(
                candidate=Candidate.model_validate(
                    assertion.model_dump(exclude={"id", "validity"})
                ),
                observed_at=source.observed_at,
                confidence=Confidence.HIGH,
                **provenance(source, GOLD.user, canonical),
            )
        )
    return drafts


def test_reconciliation_reproduces_the_gold_relations_exactly() -> None:
    drafts = gold_drafts()
    found = {
        (r.type.value, GOLD.assertions[r.from_index].id, GOLD.assertions[r.to_index].id)
        for r in reconcile(drafts)
    }
    assert found == {(r.type.value, r.from_id, r.to_id) for r in GOLD.relations}


def test_superseded_assertions_point_at_their_replacement() -> None:
    drafts = gold_drafts()
    reconcile(drafts)
    ids = [a.id for a in GOLD.assertions]
    old_phone = drafts[ids.index("g_dana_phone_old")]
    assert old_phone.superseded_by == ids.index("g_dana_phone_new")
    # A contradiction leaves both sides current: the user decides.
    assert drafts[ids.index("g_reg_coach")].superseded_by is None
    assert drafts[ids.index("g_reg_league")].superseded_by is None


def test_as_of_answers_every_temporal_query() -> None:
    drafts = gold_drafts()
    for query in GOLD.temporal_queries:
        assert as_of(drafts, query.subject, query.predicate, query.as_of) == query.expected, (
            query.id
        )


def candidate(origin: Origin) -> Candidate:
    return Candidate(
        source_id="s", kind=CandidateKind.COMMITMENT, subject="x", predicate="committed_to",
        value="x", evidence_quote="x", origin=origin,
    )  # fmt: skip


def test_confidence_is_coarse_and_depends_on_who_said_it() -> None:
    explicit, inferred = candidate(Origin.SOURCE_EXPLICIT), candidate(Origin.INFERRED)
    known = {"sender_known": True, "sender_is_user": False, "suspicious": False}
    stranger = {"sender_known": False, "sender_is_user": False, "suspicious": False}
    assert assign_confidence(explicit, **known) is Confidence.HIGH
    assert assign_confidence(explicit, **stranger) is Confidence.MEDIUM
    assert assign_confidence(inferred, **stranger) is Confidence.LOW
    flagged = {**known, "suspicious": True}
    assert assign_confidence(explicit, **flagged) is Confidence.LOW


def _draft(
    sender: str, thread: str, due: str, *, to: tuple[str, ...], low: bool = False
) -> DraftAssertion:
    from datetime import UTC, date, datetime

    from pwm.extraction.candidates import CommitmentType

    return DraftAssertion(
        candidate=Candidate(
            source_id=sender, kind=CandidateKind.COMMITMENT, subject="x", predicate="deadline",
            value="pay the invoice", evidence_quote="x", origin=Origin.SOURCE_EXPLICIT,
            commitment_type=CommitmentType.DEADLINE, due=date.fromisoformat(due),
        ),  # fmt: skip
        observed_at=datetime(2026, 9, 1 if due.endswith("20") else 2, tzinfo=UTC),
        thread_id=thread, sender_address=sender, participants=frozenset({sender, *to}),
        confidence=Confidence.LOW if low else Confidence.HIGH,
    )  # fmt: skip


def test_an_outsider_joining_a_thread_cannot_replace_what_was_said() -> None:
    bank = _draft("billing@bank.example", "t1", "2026-09-20", to=("alex@example.com",))
    intruder = _draft("x@evil.example", "t1", "2026-10-30", to=("alex@example.com",))
    relations = reconcile([bank, intruder])
    assert bank.superseded_by is None
    assert [r.type.value for r in relations] == ["contradicts"]


def test_a_low_confidence_message_neither_replaces_nor_disputes() -> None:
    bank = _draft("billing@bank.example", "t1", "2026-09-20", to=("alex@example.com",))
    spoof = _draft("billing@bank.example", "t1", "2026-10-30", to=("alex@example.com",), low=True)
    assert reconcile([bank, spoof]) == [] and bank.superseded_by is None


def test_the_original_sender_can_update_their_own_statement() -> None:
    bank = _draft("billing@bank.example", "t1", "2026-09-20", to=("alex@example.com",))
    later = _draft("billing@bank.example", "t2", "2026-10-30", to=("alex@example.com",))
    assert [r.type.value for r in reconcile([bank, later])] == ["supersedes"]
