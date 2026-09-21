"""The provider-agnostic model boundary.

Business logic depends on these protocols only. Provider SDKs are imported solely by
adapters that implement them.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from pwm.extraction.candidates import Candidate
from pwm.sources import Party, SourceRecord


class ModelUsage(BaseModel):
    """Token accounting for one model call, written to the audit log."""

    model_config = ConfigDict(frozen=True)

    stage: str
    model: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float = 0.0


class ExtractionRequest(BaseModel):
    """One unit of work for a model stage.

    `visible_text` is what the author of this message actually wrote: quoted replies
    and hidden markup are already removed. `context` holds earlier messages of the same
    thread, for understanding only; candidates must be supported by `visible_text`.
    """

    model_config = ConfigDict(frozen=True)

    source: SourceRecord
    visible_text: str
    context: tuple[str, ...] = ()
    user: Party


class TriageResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    relevant: bool
    usage: tuple[ModelUsage, ...] = ()


class ExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: tuple[Candidate, ...] = ()
    usage: tuple[ModelUsage, ...] = ()
    suspicious_content: bool = False


class Triager(Protocol):
    def is_relevant(self, request: ExtractionRequest) -> TriageResult: ...


class Extractor(Protocol):
    method: str
    prompt_version: str

    def extract(self, request: ExtractionRequest) -> ExtractionResult: ...
