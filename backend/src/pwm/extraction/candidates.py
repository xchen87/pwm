"""Candidate facts produced by an extractor.

Candidates are proposals. They carry no review state, confidence, or validity
judgement: those belong to the user and to code (TECHNICAL_BRIEF §4).
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CandidateKind(StrEnum):
    PERSON = "person"
    EVENT = "event"
    COMMITMENT = "commitment"
    THING = "thing"
    DECISION = "decision"
    # The user's own note, kept verbatim. Created by code for every capture, never by a model.
    MEMORY = "memory"


class Origin(StrEnum):
    USER_STATED = "user_stated"
    SOURCE_EXPLICIT = "source_explicit"
    INFERRED = "inferred"


class CommitmentType(StrEnum):
    PROMISE = "promise"
    DEADLINE = "deadline"


class Direction(StrEnum):
    BY_USER = "by_user"
    TO_USER = "to_user"
    BETWEEN_OTHERS = "between_others"


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Bounded on purpose: evidence is a short passage, and an unbounded field from a model
    # or a message is a way to break storage for the whole user.
    source_id: str
    kind: CandidateKind
    subject: str = Field(max_length=300)
    predicate: str = Field(max_length=64)
    value: str = Field(max_length=2000)
    evidence_quote: str = Field(min_length=1, max_length=1000)
    origin: Origin
    valid_from: date | None = None
    valid_to: date | None = None
    # Commitment-only fields.
    commitment_type: CommitmentType | None = None
    direction: Direction | None = None
    committed_by: str | None = Field(default=None, max_length=200)
    committed_to: str | None = Field(default=None, max_length=200)
    due: date | None = None

    @model_validator(mode="after")
    def _storable(self) -> "Candidate":
        for name in (
            "subject",
            "predicate",
            "value",
            "evidence_quote",
            "committed_by",
            "committed_to",
        ):
            if "\x00" in (getattr(self, name) or ""):
                raise ValueError(f"{name} contains a NUL character")
        return self
