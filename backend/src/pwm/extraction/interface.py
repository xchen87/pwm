"""The provider-agnostic extraction boundary.

Business logic depends on this protocol only. Provider SDKs are imported solely by
adapters that implement it.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from pwm.extraction.candidates import Candidate
from pwm.sources import SourceRecord


class ModelUsage(BaseModel):
    """Token accounting for one model call, written to the audit log."""

    model_config = ConfigDict(frozen=True)

    model: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float = 0.0


class ExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: tuple[Candidate, ...] = ()
    usage: tuple[ModelUsage, ...] = ()
    suspicious_content: bool = False


class Extractor(Protocol):
    def extract(self, source: SourceRecord) -> ExtractionResult: ...
