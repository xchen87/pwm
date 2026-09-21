"""Stages 7-8 tested on the gold assertions, so extractor quality is not a factor."""

from pwm.extraction.candidates import Candidate, CandidateKind, Origin
from pwm.pipeline.world import Confidence, DraftAssertion, as_of, assign_confidence, reconcile
from pwm_eval.fixture import load_fixture

FIXTURE = load_fixture()
GOLD = FIXTURE.gold


def gold_drafts() -> list[DraftAssertion]:
    drafts = []
    for assertion in GOLD.assertions:
        source = FIXTURE.source(assertion.source_id)
        drafts.append(
            DraftAssertion(
                candidate=Candidate.model_validate(
                    assertion.model_dump(exclude={"id", "validity"})
                ),
                observed_at=source.observed_at,
                thread_id=source.thread_id,
                sender_address=source.sender.address.lower() if source.sender else None,
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
