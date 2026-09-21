"""Model-backed wording against a stand-in client: what matters is what code refuses to accept."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from pwm.ask.facts import Fact
from pwm.ask.retrieval import Intent, Retrieved
from pwm.brief.items import BriefItem, ItemKind
from pwm.extraction.anthropic_writers import (
    AnthropicBriefWriter,
    AnthropicReasoner,
    _AnswerOut,
    _BriefOut,
    _WrittenOut,
)

NOW = datetime(2026, 9, 12, tzinfo=UTC)


class StandIn:
    def __init__(self, output: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(parse=self._parse)
        self._output = output

    def _parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self._output, stop_reason="end_turn")


def item(**fields: Any) -> BriefItem:
    base = {
        "kind": ItemKind.CHANGED, "assertion_id": uuid4(), "subject": "Kitchen", "predicate": "quote",
        "value": "19950", "previous_value": "18400", "is_fact": False, "confidence": "high",
        "evidence_quote": "the revised total is $19,950", "source_label": "Jordan", "observed_at": NOW,
    }  # fmt: skip
    return BriefItem(**{**base, **fields})


def worded(target: BriefItem, headline: str) -> _BriefOut:
    out = _WrittenOut(assertion_id=str(target.assertion_id), headline=headline,
                      why_it_matters="x", suggested_next_step=None)  # fmt: skip
    return _BriefOut(items=[out])


def test_an_unconfirmed_item_worded_as_fact_falls_back_to_the_template() -> None:
    target = item()
    written = AnthropicBriefWriter(StandIn(worded(target, "The kitchen now costs $19,950"))).write(
        [target]
    )  # type: ignore[arg-type]
    assert written[0].headline.startswith("It looks like")


def test_a_number_the_item_does_not_contain_is_rejected() -> None:
    target = item()
    written = AnthropicBriefWriter(
        StandIn(worded(target, "It looks like the kitchen is now $21,000"))
    ).write([target])  # type: ignore[arg-type]
    assert "$19,950" in written[0].headline and "21,000" not in written[0].headline


def test_good_wording_is_kept_and_the_model_cannot_add_or_drop_items() -> None:
    first, second = item(), item(subject="Dentist")
    out = worded(first, "It looks like the kitchen quote rose to 19950 from 18400")
    out.items.append(
        _WrittenOut(
            assertion_id=str(uuid4()),
            headline="Possible: invented",
            why_it_matters="x",
            suggested_next_step=None,
        )
    )
    written = AnthropicBriefWriter(StandIn(out)).write([first, second])  # type: ignore[arg-type]
    assert [w.item.assertion_id for w in written] == [first.assertion_id, second.assertion_id]
    assert written[0].headline.startswith("It looks like the kitchen quote rose")
    assert written[1].headline.startswith("It looks like Dentist")


def fact(id: str) -> Fact:
    return Fact(id=id, kind="commitment", subject="Alex", predicate="committed_to", value="send the deck",
                evidence_quote="I'll send the deck", observed_at=NOW)  # fmt: skip


def test_an_answer_may_cite_only_what_it_was_given() -> None:
    retrieved = Retrieved(intent=Intent.LOOKUP, facts=[fact("1")])
    made_up = AnthropicReasoner(StandIn(_AnswerOut(text="You owe $500.", cited_ids=["99"])))  # type: ignore[arg-type]
    answer = made_up.answer("q", retrieved)
    assert not answer.grounded and answer.cited == []

    honest = AnthropicReasoner(
        StandIn(_AnswerOut(text="Possibly: send the deck.", cited_ids=["1"]))
    )  # type: ignore[arg-type]
    answer = honest.answer("q", retrieved)
    assert answer.grounded and [f.id for f in answer.cited] == ["1"] and answer.caveat


def test_no_evidence_means_no_model_call() -> None:
    client = StandIn(_AnswerOut(text="anything", cited_ids=[]))
    answer = AnthropicReasoner(client).answer("q", Retrieved(intent=Intent.LOOKUP, facts=[]))  # type: ignore[arg-type]
    assert not answer.grounded and client.calls == []
