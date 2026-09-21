"""The adapter against a stand-in client. Nothing here calls the network."""

from types import SimpleNamespace
from typing import Any

from pwm.extraction.anthropic_adapter import AnthropicExtractor, AnthropicTriager
from pwm.extraction.interface import ExtractionRequest
from pwm.extraction.prompts import ExtractionOutput, ModelCandidate, TriageOutput, extraction_prefix
from pwm.pipeline.text import visible_text
from pwm.sources import Party
from pwm_eval.fixture import load_fixture

FIXTURE = load_fixture()


def request_for(source_id: str, user: Party = FIXTURE.gold.user) -> ExtractionRequest:
    source = FIXTURE.source(source_id)
    return ExtractionRequest(source=source, visible_text=visible_text(source), user=user)


def raw(**overrides: Any) -> ModelCandidate:
    fields = {
        "kind": "commitment", "subject": "Alex Rivera", "predicate": "committed_to",
        "value": "send the Q3 numbers", "evidence_quote": "I'll send you the Q3 numbers by Friday.",
        "origin": "source_explicit", "valid_from": None, "valid_to": None,
        "commitment_type": "promise", "direction": "by_user", "committed_by": "Alex Rivera",
        "committed_to": "Tom Okafor", "due": "2026-09-11",
    }  # fmt: skip
    return ModelCandidate(**{**fields, **overrides})


class StandInClient:
    def __init__(self, output: Any, stop_reason: str = "end_turn") -> None:
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(parse=self._parse)
        self._output, self._stop_reason = output, stop_reason

    def _parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        usage = SimpleNamespace(
            input_tokens=200,
            output_tokens=100,
            cache_read_input_tokens=3000,
            cache_creation_input_tokens=0,
        )
        return SimpleNamespace(
            parsed_output=self._output, usage=usage, stop_reason=self._stop_reason
        )


def test_the_cached_prefix_is_identical_for_every_source_and_user() -> None:
    client = StandInClient(ExtractionOutput(suspicious_content=False, candidates=[]))
    extractor = AnthropicExtractor(client)  # type: ignore[arg-type]
    extractor.extract(request_for("e_q3_1"))
    extractor.extract(
        request_for("e_lease_2", Party(name="Someone Else", address="else@example.com"))
    )

    first, second = (call["system"] for call in client.calls)
    assert first == second
    assert first[-1]["cache_control"] == {"type": "ephemeral"}
    prefix = first[0]["text"]
    for volatile in (
        "Alex Rivera",
        "alex.rivera@example.com",
        "2026-09",
        "Q3 numbers",
        "Whitfield",
    ):
        assert volatile not in prefix
    assert "Q3 numbers" in client.calls[0]["messages"][0]["content"]
    assert "Message date: 2026-09-07" in client.calls[0]["messages"][0]["content"]


def test_the_prompt_never_borrows_from_the_eval_fixture() -> None:
    prefix = extraction_prefix()
    for assertion in FIXTURE.gold.assertions:
        assert assertion.evidence_quote.replace("\n", " ") not in prefix
        assert assertion.value not in prefix or len(assertion.value) < 8, assertion.id
    for person in FIXTURE.gold.people:
        assert person.name.split()[-1] not in prefix, person.name


def test_model_output_is_validated_and_usage_is_costed() -> None:
    output = ExtractionOutput(
        suspicious_content=False,
        candidates=[raw(), raw(kind="prophecy"), raw(due="next Friday")],
    )
    result = AnthropicExtractor(StandInClient(output)).extract(request_for("e_q3_1"))  # type: ignore[arg-type]
    assert len(result.candidates) == 1
    assert result.candidates[0].source_id == "e_q3_1"
    assert result.candidates[0].due is not None
    usage = result.usage[0]
    assert (usage.model, usage.cache_read_input_tokens) == ("claude-opus-5", 3000)
    assert usage.cost_usd == round((200 * 5 + 3000 * 0.5 + 100 * 25) / 1_000_000, 6)


def test_a_refusal_yields_nothing_and_flags_the_source() -> None:
    client = StandInClient(None, stop_reason="refusal")
    result = AnthropicExtractor(client).extract(request_for("x_ignore"))  # type: ignore[arg-type]
    assert result.candidates == () and result.suspicious_content


def test_triage_fails_open() -> None:
    assert AnthropicTriager(StandInClient(None)).is_relevant(request_for("e_q3_1")).relevant  # type: ignore[arg-type]
    screened = AnthropicTriager(StandInClient(TriageOutput(relevant=False)))  # type: ignore[arg-type]
    assert not screened.is_relevant(request_for("n_human_01")).relevant
