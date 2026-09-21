"""Anthropic implementation of the model stages. The only module that imports the SDK.

Not exercised against the live API in this repository's tests: those use a stand-in
client. Run `python -m pwm_eval.run --system anthropic` with credentials to evaluate it.
"""

from datetime import date
from typing import Any

import anthropic
from pydantic import ValidationError

from pwm.extraction.candidates import Candidate
from pwm.extraction.interface import (
    ExtractionRequest,
    ExtractionResult,
    ModelUsage,
    TriageResult,
)
from pwm.extraction.prompts import (
    PROMPT_VERSION,
    TRIAGE_PROMPT_VERSION,
    TRIAGE_SYSTEM,
    ExtractionOutput,
    ModelCandidate,
    TriageOutput,
    extraction_prefix,
    user_message,
)

# USD per million tokens: (input, output). Cache reads bill at 0.1x input, 5-minute writes at 1.25x.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _usage(stage: str, model: str, version: str, usage: Any) -> ModelUsage:
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    cost = (
        usage.input_tokens * price_in
        + read * price_in * 0.1
        + written * price_in * 1.25
        + usage.output_tokens * price_out
    ) / 1_000_000
    return ModelUsage(
        stage=stage, model=model, prompt_version=version, input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens, cache_read_input_tokens=read,
        cache_creation_input_tokens=written, cost_usd=round(cost, 6),
    )  # fmt: skip


def _to_candidate(raw: ModelCandidate, source_id: str) -> Candidate | None:
    """Model output is untrusted too: anything that does not validate is dropped."""
    try:
        fields = raw.model_dump()
        for name in ("valid_from", "valid_to", "due"):
            fields[name] = date.fromisoformat(fields[name][:10]) if fields[name] else None
        return Candidate(source_id=source_id, **fields)
    except (ValidationError, ValueError):
        return None


class AnthropicTriager:
    def __init__(self, client: anthropic.Anthropic, model: str = "claude-haiku-4-5") -> None:
        self._client, self._model = client, model

    def is_relevant(self, request: ExtractionRequest) -> TriageResult:
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=256,
            system=[
                {"type": "text", "text": TRIAGE_SYSTEM, "cache_control": {"type": "ephemeral"}}
            ],
            messages=[{"role": "user", "content": f"<source>\n{request.visible_text}\n</source>"}],
            output_format=TriageOutput,
        )
        usage = _usage("triage", self._model, TRIAGE_PROMPT_VERSION, response.usage)
        parsed = response.parsed_output
        # Fail open: a message we could not screen is extracted rather than silently lost.
        return TriageResult(relevant=parsed.relevant if parsed else True, usage=(usage,))


class AnthropicExtractor:
    method = "anthropic"
    prompt_version = PROMPT_VERSION

    def __init__(self, client: anthropic.Anthropic, model: str = "claude-opus-5") -> None:
        self._client, self._model = client, model
        self.method = f"anthropic:{model}"

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=16000,
            # The frozen prefix, with the cache breakpoint at its end. Everything that
            # varies per source is in the user message below.
            system=[
                {
                    "type": "text",
                    "text": extraction_prefix(),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message(request)}],
            output_format=ExtractionOutput,
        )
        usage = _usage("extraction", self._model, self.prompt_version, response.usage)
        parsed = response.parsed_output
        if response.stop_reason == "refusal" or parsed is None:
            return ExtractionResult(usage=(usage,), suspicious_content=True)
        candidates = (_to_candidate(raw, request.source.id) for raw in parsed.candidates)
        return ExtractionResult(
            candidates=tuple(c for c in candidates if c is not None),
            usage=(usage,),
            suspicious_content=parsed.suspicious_content,
        )
