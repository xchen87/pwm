from collections.abc import Sequence
from datetime import date

from pwm.extraction.candidates import Candidate, CandidateKind, Origin
from pwm.sources import Party, SourceRecord
from pwm_eval.fixture import load_fixture
from pwm_eval.metrics import evaluate, match
from pwm_eval.systems import BaselineSystem, OracleSystem, SourceTrace, SystemOutput

FIXTURE = load_fixture()


def test_oracle_scores_perfectly() -> None:
    report = evaluate(OracleSystem(FIXTURE.gold), FIXTURE)
    for block in (report.commitments, report.decisions, report.facts,
                  report.people_addresses, report.people_resolution_pairs,
                  report.relations):  # fmt: skip
        assert (block.precision, block.recall) == (1.0, 1.0)
    assert report.commitment_direction_accuracy == 1.0
    assert report.commitment_due_accuracy == 1.0
    assert report.temporal_accuracy == 1.0
    assert (report.ask_hit_rate, report.ask_false_answer_rate) == (1.0, 0.0)
    assert report.quote_verification_pass_rate == 1.0
    assert report.noise_reaching_model_rate == 0.0
    assert report.signal_emails_dropped_rate == 0.0
    assert report.injection_clean


def test_baseline_is_silent_and_scores_zero_recall() -> None:
    report = evaluate(BaselineSystem(), FIXTURE)
    assert report.commitments.recall == 0.0
    assert report.commitments.precision is None  # nothing predicted: undefined, not perfect
    assert report.temporal_accuracy == 0.0
    assert report.signal_emails_dropped_rate == 1.0
    assert report.injection_clean


class GullibleSystem:
    """Believes whatever a message says, including the attacker's text."""

    name = "gullible"

    def run(self, sources: Sequence[SourceRecord], user: Party) -> SystemOutput:
        traces = []
        for source in sources:
            spans = [s for s in FIXTURE.gold.injected_spans if s.source_id == source.id]
            candidates = tuple(
                Candidate(
                    source_id=source.id,
                    kind=CandidateKind.COMMITMENT,
                    subject="Alex Rivera",
                    predicate="committed_to",
                    value="whatever the email said",
                    evidence_quote=span.text,
                    origin=Origin.SOURCE_EXPLICIT,
                )  # fmt: skip
                for span in spans
            )
            traces.append(
                SourceTrace(source_id=source.id, reached_model=True, candidates=candidates)
            )
        return SystemOutput(traces=tuple(traces))

    def as_of(self, subject: str, predicate: str, when: date) -> str | None:
        return None

    def ask(self, question: str, today: date) -> list[Candidate]:
        return []


def test_injection_suite_catches_a_gullible_system() -> None:
    report = evaluate(GullibleSystem(), FIXTURE)
    assert report.injection_violations == len(FIXTURE.gold.injected_spans)
    assert not report.injection_clean
    assert report.commitments.precision == 0.0
    assert report.noise_reaching_model_rate == 1.0


def test_quoted_reply_is_not_credited_to_the_replier() -> None:
    # Alex's promise is quoted inside Tom's reply (e_q3_2). Extracting it there is an error.
    requoted = Candidate(
        source_id="e_q3_2", kind=CandidateKind.COMMITMENT, subject="Alex Rivera",
        predicate="committed_to", value="send the Q3 numbers",
        evidence_quote="I'll send you the Q3 numbers by Friday.", origin=Origin.SOURCE_EXPLICIT,
    )  # fmt: skip
    gold_in_reply = [a for a in FIXTURE.gold.assertions if a.source_id == "e_q3_2"]
    assert match([requoted], gold_in_reply) == []
