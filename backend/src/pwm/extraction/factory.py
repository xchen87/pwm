"""Chooses the model stages from configuration, so nothing else knows which provider is in use."""

from pwm.config import get_settings
from pwm.extraction.interface import Extractor, Triager
from pwm.pipeline.heuristic import HeuristicExtractor, HeuristicTriager


def build_stages() -> tuple[Triager, Extractor]:
    settings = get_settings()
    if settings.extractor == "heuristic":
        return HeuristicTriager(), HeuristicExtractor()
    if settings.extractor == "anthropic":
        import anthropic  # imported here so the SDK is only needed when it is selected

        from pwm.extraction.anthropic_adapter import AnthropicExtractor, AnthropicTriager

        client = anthropic.Anthropic()
        return (
            AnthropicTriager(client, settings.triage_model),
            AnthropicExtractor(client, settings.extraction_model),
        )
    raise ValueError(f"unknown PWM_EXTRACTOR: {settings.extractor}")
