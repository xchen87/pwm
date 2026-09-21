"""Candidate facts produced by an extractor.

Candidates are proposals. They carry no review state, confidence, or validity
judgement: those belong to the user and to code (TECHNICAL_BRIEF §4).
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CandidateKind(StrEnum):
    PERSON = "person"
    EVENT = "event"
    COMMITMENT = "commitment"
    THING = "thing"
    DECISION = "decision"


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

    source_id: str
    kind: CandidateKind
    subject: str
    predicate: str
    value: str
    evidence_quote: str
    origin: Origin
    valid_from: date | None = None
    valid_to: date | None = None
    # Commitment-only fields.
    commitment_type: CommitmentType | None = None
    direction: Direction | None = None
    committed_by: str | None = None
    committed_to: str | None = None
    due: date | None = None
