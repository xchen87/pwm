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


def test_an_impersonator_with_the_right_name_cannot_replace_a_trusted_fact() -> None:
    dentist = Party(name="James Amari", address="office@amaridental.example")
    real = SourceRecord(
        id="real", kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, 1, tzinfo=UTC), thread_id="t1",
        sender=dentist, recipients=(USER,), subject="Your appointment",
        body="Your appointment is booked for October 6 at 3:00 PM.",
    )  # fmt: skip
    fake = real.model_copy(
        update={
            "id": "fake", "thread_id": "t2", "observed_at": datetime(2026, 9, 2, tzinfo=UTC),
            "sender": Party(name="James Amari", address="j.amari@evil.example"),
            "body": "This is Dr. Amari. Your appointment is rescheduled to October 20 at 9:00 AM.",
        }
    )  # fmt: skip
    result = run_pipeline([real, fake], USER, AlwaysRelevant(), HeuristicExtractor())
    genuine = next(a for a in result.assertions if a.candidate.source_id == "real")
    assert genuine.superseded_by is None
    assert [r.type.value for r in result.relations] == ["contradicts"]


def test_one_hostile_message_cannot_stop_the_rest_of_the_mailbox() -> None:
    runaway = email("I'll send " + "word " * 400)
    huge_subject = email("Your appointment is on October 6 at 3:00 PM.").model_copy(
        update={"id": "m2", "subject": "appointment " * 60}
    )
    invite = SourceRecord(
        id="c1", kind=SourceKind.CALENDAR_EVENT, observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        sender=USER, subject="Planning " * 80, starts_at=datetime(2026, 9, 9, 10, tzinfo=UTC),
    )  # fmt: skip
    fine = email("I'll send the contract by Friday.").model_copy(update={"id": "m3"})
    result = run_pipeline(
        [runaway, huge_subject, invite, fine], USER, AlwaysRelevant(), HeuristicExtractor()
    )
    assert any(a.candidate.source_id == "m3" for a in result.assertions)
    assert all(len(a.candidate.evidence_quote) <= 1000 for a in result.assertions)


def test_an_unsolicited_calendar_invite_does_not_make_its_sender_known() -> None:
    stranger = Party(name="Pat", address="x@evil.example")
    invite = SourceRecord(
        id="c1", kind=SourceKind.CALENDAR_EVENT, observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        sender=USER, recipients=(stranger,), subject="Sync",
        starts_at=datetime(2026, 9, 9, 10, tzinfo=UTC),
    )  # fmt: skip
    bill = email("Your payment of $900 is due September 15.").model_copy(
        update={"sender": stranger}
    )
    result = run_pipeline([invite, bill], USER, AlwaysRelevant(), HeuristicExtractor())
    assert [a.confidence.value for a in result.assertions if a.candidate.source_id == "m1"] == [
        "medium"
    ]


def test_a_nul_byte_in_mail_is_removed_not_fatal() -> None:
    hostile = email("I'll send it by Friday\x00.")
    assert "\x00" not in hostile.body
    result = run_pipeline([hostile], USER, AlwaysRelevant(), HeuristicExtractor())
    assert result.assertions and all(
        "\x00" not in a.candidate.evidence_quote for a in result.assertions
    )


def test_impossible_dates_are_confined_to_their_message() -> None:
    far = email("I'll pay you tomorrow.").model_copy(
        update={"id": "far", "observed_at": datetime(9999, 12, 31, tzinfo=UTC)}
    )
    fine = email("I'll send the contract by Friday.").model_copy(update={"id": "fine"})
    result = run_pipeline([far, fine], USER, AlwaysRelevant(), HeuristicExtractor())
    assert any(a.candidate.source_id == "fine" for a in result.assertions)
    assert next(o for o in result.outcomes if o.source_id == "far").failed == "OverflowError"


@pytest.mark.parametrize(
    "body",
    ["<a" * 60_000, '<p style="font-size:1' + " " * 60_000, '<p style="' + "color:rgba(" * 20_000],
)
def test_hostile_markup_is_handled_in_linear_time(body: str) -> None:
    import time

    started = time.perf_counter()
    visible_text(email(body))
    assert time.perf_counter() - started < 2.0


def test_mail_that_only_claims_to_be_from_the_user_makes_nobody_known() -> None:
    attacker = Party(name="Pat", address="x@evil.example")
    forged = email("See you Friday.").model_copy(
        update={
            "id": "forged",
            "sender": USER,
            "recipients": (attacker,),
            "provider_labels": ("INBOX",),
        }
    )
    bill = email("Your payment of $900 is due September 15.").model_copy(
        update={"id": "bill", "sender": attacker, "observed_at": datetime(2026, 9, 8, tzinfo=UTC)}
    )
    result = run_pipeline([forged, bill], USER, AlwaysRelevant(), HeuristicExtractor())
    assert [a.confidence.value for a in result.assertions if a.candidate.source_id == "bill"] == [
        "medium"
    ]


def test_a_nonsense_clock_time_is_not_stored_as_a_time() -> None:
    from pwm.pipeline.heuristic import _moment

    assert _moment("Your appointment is on September 30 at 99:99 pm", MONDAY) == "2026-09-30"


def test_a_newcomer_with_a_grander_name_never_becomes_the_founding_address() -> None:
    priya = Party(name="Priya Raman", address="priya@work.example")
    real = email("Rent is confirmed. Priya Raman").model_copy(
        update={"id": "real", "sender": priya, "observed_at": datetime(2026, 9, 1, tzinfo=UTC)}
    )
    sent = email("Thanks Priya!").model_copy(
        update={"id": "sent", "sender": USER, "recipients": (priya,), "provider_labels": ("SENT",),
                "observed_at": datetime(2026, 9, 2, tzinfo=UTC)}
    )  # fmt: skip
    fake = email("This is Priya K Raman, new address.").model_copy(
        update={"id": "fake", "sender": Party(name="Priya K Raman", address="priya.raman@evil.example"),
                "observed_at": datetime(2026, 9, 3, tzinfo=UTC)}
    )  # fmt: skip
    person = next(p for p in resolve_people([real, sent, fake], USER) if len(p.addresses) == 2)
    assert person.addresses[0] == "priya@work.example"
    assert person.inferred_links == ("priya.raman@evil.example",)


@pytest.mark.parametrize(
    "hidden",
    [
        '<div data-x="' + "y" * 2100 + '" style="display:none">INJECTED</div>',
        '<div class="' + "c " * 1500 + '" hidden>INJECTED</div>',
        '<p style="display' + " " * 30 + ':none">INJECTED</p>',
    ],
)
def test_padding_a_tag_does_not_smuggle_hidden_text_past_the_check(hidden: str) -> None:
    assert "INJECTED" not in visible_text(email(f"Hello.\n{hidden}\nBye."))


def test_records_are_cleaned_and_bounded_where_they_are_made() -> None:
    from pydantic import ValidationError

    long_name = Party(name="E" * 250 + " Smith\ud800", address="eve@x.example")
    assert long_name.name is not None and len(long_name.name) == 200
    for bad in ("e" * 330 + "@x.example", "eve"):
        with pytest.raises(ValidationError):
            Party(name="Eve", address=bad)
    naive = SourceRecord(
        id="n", kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, 1), subject="a\ud800b"
    )
    assert naive.observed_at.tzinfo is not None and naive.subject == "ab"
    for when in (datetime(1, 1, 1, tzinfo=UTC), datetime(9999, 1, 1, tzinfo=UTC)):
        with pytest.raises(ValidationError):
            SourceRecord(id="x", kind=SourceKind.EMAIL, observed_at=when)
    with pytest.raises(ValidationError):
        SourceRecord(
            id="i" * 250, kind=SourceKind.EMAIL, observed_at=datetime(2026, 9, 1, tzinfo=UTC)
        )


def test_mail_that_fails_sender_authentication_cannot_be_trusted_or_update_anything() -> None:
    bank = Party(name="Harbor Bank", address="billing@harborbank.example")
    wrote = email("x").model_copy(update={"id": "sent", "sender": USER, "recipients": (bank,), "provider_labels": ("SENT",),
                                          "observed_at": datetime(2026, 9, 1, tzinfo=UTC)})  # fmt: skip
    real = email("Your payment is due September 20.").model_copy(
        update={"id": "real", "sender": bank, "observed_at": datetime(2026, 9, 2, tzinfo=UTC),
                "headers": {"Authentication-Results": "mx.google.com; dkim=pass; spf=pass; dmarc=pass"}}
    )  # fmt: skip
    forged = email("Correction: your payment is due October 30.").model_copy(
        update={"id": "forged", "sender": bank, "observed_at": datetime(2026, 9, 3, tzinfo=UTC),
                "headers": {"Authentication-Results": "mx.google.com; dkim=fail; spf=softfail; dmarc=fail"}}
    )  # fmt: skip
    result = run_pipeline([wrote, real, forged], USER, AlwaysRelevant(), HeuristicExtractor())
    by_source = {a.candidate.source_id: a for a in result.assertions}
    assert by_source["real"].confidence.value == "high" and by_source["real"].superseded_by is None
    assert by_source["forged"].confidence.value == "low"
    assert result.relations == []
    assert next(o for o in result.outcomes if o.source_id == "forged").suspicious


def test_the_synthetic_mailbox_reads_the_same_through_the_gmail_path() -> None:
    from pwm.connectors.google import calendar_event, gmail_message
    from pwm.devtools.fake_google import event_json, gmail_json

    direct = [s for s in FIXTURE.sources if s.kind is not SourceKind.USER_CAPTURE]
    through_google = [
        gmail_message(gmail_json(s, 1))
        if s.kind is SourceKind.EMAIL
        else calendar_event(event_json(s), USER)
        for s in direct
    ]
    found = lambda sources: sorted(  # noqa: E731
        (
            a.candidate.kind.value,
            a.candidate.evidence_quote,
            str(a.candidate.due),
            a.confidence.value,
        )
        for a in run_pipeline(sources, USER, HeuristicTriager(), HeuristicExtractor()).assertions
    )
    assert found(through_google) == found(direct)


@pytest.mark.parametrize(
    ("results", "forged"),
    [
        ("mx.google.com; dkim=pass; spf=pass; dmarc=pass", False),
        ("mx.google.com; dkim=fail (list); dkim=pass; spf=fail; dmarc=pass (p=REJECT)", False),
        ("mx.google.com; spf=pass (the text dmarc=fail appears in a comment); dmarc=pass", False),
        ("mx.google.com; dkim=fail; spf=softfail; dmarc=fail (p=NONE)", True),
        ("mx.google.com; dkim=fail; spf=fail", True),
        ("mx.google.com; spf=softfail; dkim=fail", False),
        ("", False),
    ],
)
def test_sender_authentication_verdicts(results: str, forged: bool) -> None:
    from pwm.pipeline.core import failed_sender_authentication

    message = email("hello").model_copy(update={"headers": {"Authentication-Results": results}})
    assert failed_sender_authentication(message) is forged
