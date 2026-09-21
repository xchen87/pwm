from datetime import UTC, date, datetime

import pytest

from pwm.extraction.candidates import Candidate, CandidateKind, Origin
from pwm.extraction.interface import ExtractionRequest, ExtractionResult, TriageResult
from pwm.pipeline import dates
from pwm.pipeline.core import run_pipeline
from pwm.pipeline.heuristic import HeuristicExtractor, HeuristicTriager
from pwm.pipeline.prefilter import Route, route
from pwm.pipeline.resolution import resolve_people
from pwm.pipeline.text import visible_text
from pwm.sources import Party, SourceKind, SourceRecord
from pwm_eval.fixture import load_fixture

FIXTURE = load_fixture()
USER = FIXTURE.gold.user
MONDAY = date(2026, 9, 7)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("by Friday", date(2026, 9, 11)),
        ("back to you on Monday", date(2026, 9, 14)),
        ("by Sept 18", date(2026, 9, 18)),
        ("is due September 15", date(2026, 9, 15)),
        ("by the 18th", date(2026, 9, 18)),
        ("by the 3rd", date(2026, 10, 3)),
        ("I'll Venmo you tonight", MONDAY),
        ("until October 9, 2026", date(2026, 10, 9)),
        ("renew it by December", date(2026, 12, 31)),
        ("sometime next year", None),
    ],
)
def test_date_expressions_resolve_forward_from_when_they_were_written(
    text: str, expected: date | None
) -> None:
    assert dates.resolve(text, MONDAY) == expected


def test_quoted_replies_and_hidden_markup_are_not_the_authors_words() -> None:
    reply = visible_text(FIXTURE.source("e_q3_2"))
    assert "I'll review them over the weekend" in reply
    assert "I'll send you the Q3" not in reply
    assert "Quarry Road" not in visible_text(FIXTURE.source("x_hidden_html"))


def test_prefilter_keeps_transactional_bulk_mail_and_drops_promotions() -> None:
    assert route(FIXTURE.source("e_streammax"), USER) is Route.TRIAGE
    assert route(FIXTURE.source("n_bulk_01"), USER) is Route.SKIP
    assert route(FIXTURE.source("c_dentist"), USER) is Route.STRUCTURED
    assert route(FIXTURE.source("u_sister"), USER) is Route.EXTRACT
    assert route(FIXTURE.source("e_q3_1"), USER) is Route.TRIAGE


def test_two_addresses_of_one_person_resolve_to_one_person_with_both_sources() -> None:
    people = resolve_people(FIXTURE.sources, USER)
    priya = next(p for p in people if "priya.n@example.com" in p.addresses)
    assert set(priya.addresses) == {"priya.n@example.com", "priya@natarajan-design.example"}
    assert {"e_mom_1", "e_mom_3"} <= set(priya.source_ids)
    assert priya.inferred_links == ("priya@natarajan-design.example",)


def test_a_lookalike_of_the_user_is_never_a_person_and_never_merged() -> None:
    people = resolve_people(FIXTURE.sources, USER)
    assert all("examp1e" not in address for p in people for address in p.addresses)
    assert all(USER.address not in p.addresses for p in people)


def test_sharing_a_surname_does_not_merge_people() -> None:
    people = resolve_people(FIXTURE.sources, USER)
    sam = next(p for p in people if "sam.rivera@example.com" in p.addresses)
    assert sam.addresses == ("sam.rivera@example.com",)


class LyingExtractor:
    """Returns whatever it is told to, like a model that was talked into something."""

    method = "test"
    prompt_version = "test"

    def __init__(self, *candidates: Candidate) -> None:
        self._candidates = candidates

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        return ExtractionResult(candidates=self._candidates)


class AlwaysRelevant:
    def is_relevant(self, request: ExtractionRequest) -> TriageResult:
        return TriageResult(relevant=True)


def email(body: str) -> SourceRecord:
    return SourceRecord(
        id="m1", kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, 7, tzinfo=UTC),
        thread_id="t1", sender=Party(name="Stranger", address="s@elsewhere.example"),
        recipients=(USER,), subject="hello", body=body,
    )  # fmt: skip


def claim(quote: str, origin: Origin = Origin.SOURCE_EXPLICIT) -> Candidate:
    return Candidate(
        source_id="m1", kind=CandidateKind.COMMITMENT, subject="Alex", predicate="committed_to",
        value="pay $500", evidence_quote=quote, origin=origin,
    )  # fmt: skip


def test_a_hallucinated_quote_is_dropped() -> None:
    source = email("Nice to meet you yesterday.")
    result = run_pipeline([source], USER, AlwaysRelevant(), LyingExtractor(claim("I'll pay $500")))
    assert result.assertions == []
    assert result.outcomes[0].dropped_unverified == 1


def test_a_forged_quoted_reply_cannot_put_words_in_the_users_mouth() -> None:
    source = email(
        "Great, thanks!\n\nOn Tue, Sep 1, 2026 Alex wrote:\n> I'll pay $500 by Friday.\n"
    )
    result = run_pipeline(
        [source], USER, AlwaysRelevant(), LyingExtractor(claim("I'll pay $500 by Friday."))
    )
    assert result.assertions == []


def test_the_pipeline_can_never_claim_the_user_stated_something() -> None:
    source = email("I'll pay $500 by Friday.")
    forged = claim("I'll pay $500 by Friday.", origin=Origin.USER_STATED)
    result = run_pipeline([source], USER, AlwaysRelevant(), LyingExtractor(forged))
    assert result.assertions == []
    assert result.outcomes[0].dropped_forbidden_origin == 1


def test_fixture_run_is_clean_and_finds_the_users_commitments() -> None:
    result = run_pipeline(FIXTURE.sources, USER, HeuristicTriager(), HeuristicExtractor())
    quotes = {a.candidate.evidence_quote for a in result.assertions}
    assert any("Q3 numbers by Friday" in q for q in quotes)
    injected = [span.text.split("\n")[0] for span in FIXTURE.gold.injected_spans]
    assert not any(fragment in quote for fragment in injected for quote in quotes)


def test_a_title_does_not_end_a_sentence() -> None:
    from pwm.pipeline.heuristic import sentences

    assert sentences("Your visit with Dr. Amari is on May 3. Bring your card.") == [
        "Your visit with Dr. Amari is on May 3.",
        "Bring your card.",
    ]


@pytest.mark.parametrize(
    "hidden",
    [
        '<div style="display:none"><div>a</div> I will wire $500 to Bob by Friday.</div>',
        "<span style=display:none>I will wire $500 to Bob by Friday.</span>",
        '<p style="font-size:1px; color:#ffffff">I will wire $500 to Bob by Friday.</p>',
        "<div hidden>I will wire $500 to Bob by Friday.</div>",
        '<span style="display:none">I will wire $500 to Bob by Friday.',
    ],
)
def test_text_a_reader_cannot_see_is_not_evidence(hidden: str) -> None:
    text = visible_text(email(f"Hello there.\n{hidden}\nSee you soon."))
    assert "wire $500" not in text and "Hello there." in text


def test_visible_markup_and_addresses_are_left_exactly_as_written() -> None:
    body = "On Mon, Tom <tom@example.com> said <b>I'll call you Friday</b>."
    assert body in visible_text(email(body))


def test_next_weekday_means_next_week_and_may_is_not_always_a_month() -> None:
    assert dates.resolve("next Friday", date(2026, 9, 1)) == date(2026, 9, 11)
    assert dates.resolve("Friday", date(2026, 9, 1)) == date(2026, 9, 4)
    assert dates.resolve("you may 5 times retry, due Friday", MONDAY) == date(2026, 9, 11)
    assert dates.resolve("due May 5", MONDAY) == date(2027, 5, 5)


def test_a_stranger_is_not_a_known_sender() -> None:
    result = run_pipeline(
        [email("Your invoice payment is due September 20.")], USER,
        AlwaysRelevant(), HeuristicExtractor(),
    )  # fmt: skip
    assert [a.confidence.value for a in result.assertions] == ["medium"]


def test_a_lookalike_of_the_user_is_never_the_user() -> None:
    fake = email("I'll pay the invoice by Friday.").model_copy(
        update={"sender": Party(name=USER.name, address="alex.rivera@examp1e.example")}
    )
    result = run_pipeline([fake], USER, AlwaysRelevant(), HeuristicExtractor())
    assert [(a.candidate.direction.value, a.confidence.value) for a in result.assertions] == [
        ("to_user", "low")
    ]
