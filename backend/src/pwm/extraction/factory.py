"""Chooses the model stages from configuration, so nothing else knows which provider is in use."""

from pwm.ask.answer import Reasoner, TemplateReasoner
from pwm.brief.writer import BriefWriter, TemplateBriefWriter
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


def build_writers() -> tuple[BriefWriter, Reasoner]:
    """Who words briefs and answers. Templates need nothing; the model-backed pair is
    selected with the same switch as extraction."""
    settings = get_settings()
    if settings.extractor == "anthropic":
        import anthropic

        from pwm.extraction.anthropic_writers import AnthropicBriefWriter, AnthropicReasoner

        client = anthropic.Anthropic()
        return (
            AnthropicBriefWriter(client, settings.extraction_model),
            AnthropicReasoner(client, settings.extraction_model),
        )
    return TemplateBriefWriter(), TemplateReasoner()
