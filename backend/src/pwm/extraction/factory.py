"""Chooses the model stages from configuration, so nothing else knows which provider is in use."""

from typing import TYPE_CHECKING

from pwm.ask.answer import Reasoner, TemplateReasoner
from pwm.brief.writer import BriefWriter, TemplateBriefWriter
from pwm.config import get_settings
from pwm.extraction.interface import Extractor, Triager
from pwm.pipeline.heuristic import HeuristicExtractor, HeuristicTriager

if TYPE_CHECKING:
    import anthropic


class ProviderNotConfigured(RuntimeError):
    """The model path is selected but there are no credentials for it."""


def _anthropic_client() -> "anthropic.Anthropic":
    import anthropic  # imported here so the SDK is only needed when it is selected

    client = anthropic.Anthropic()
    # Without this the first request fails deep inside the SDK with an unhelpful TypeError.
    if not (getattr(client, "api_key", None) or getattr(client, "auth_token", None)):
        raise ProviderNotConfigured(
            "PWM_EXTRACTOR=anthropic needs credentials (ANTHROPIC_API_KEY or `ant auth login`)"
        )
    return client


def build_stages() -> tuple[Triager, Extractor]:
    settings = get_settings()
    if settings.extractor == "heuristic":
        return HeuristicTriager(), HeuristicExtractor()
    if settings.extractor == "anthropic":
        from pwm.extraction.anthropic_adapter import AnthropicExtractor, AnthropicTriager

        client = _anthropic_client()
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
        from pwm.extraction.anthropic_writers import AnthropicBriefWriter, AnthropicReasoner

        client = _anthropic_client()
        return (
            AnthropicBriefWriter(client, settings.extraction_model),
            AnthropicReasoner(client, settings.extraction_model),
        )
    return TemplateBriefWriter(), TemplateReasoner()


def provider_errors() -> tuple[type[Exception], ...]:
    """Exception types that mean "the model provider failed", for the API to turn into a
    clean 503. Empty when no provider is in use."""
    if get_settings().extractor != "anthropic":
        return ()
    import anthropic

    return (anthropic.AnthropicError, ProviderNotConfigured)
