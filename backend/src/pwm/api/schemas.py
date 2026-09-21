from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class SourceSummary(BaseModel):
    kind: str
    sender_name: str | None
    sender_address: str | None
    subject: str
    observed_at: datetime


class CommitmentItem(BaseModel):
    id: UUID
    what: str
    commitment_type: str | None
    direction: str | None
    committed_by: str | None
    committed_to: str | None
    due: date | None
    overdue: bool
    status: str | None
    origin: str
    review: str
    confidence: str
    evidence_quote: str
    has_conflict: bool
    source: SourceSummary


class RelatedAssertion(BaseModel):
    id: UUID
    relation: str
    what: str
    due: date | None
    evidence_quote: str
    source: SourceSummary


class AssertionDetail(CommitmentItem):
    kind: str
    subject: str
    predicate: str
    extraction_method: str
    recorded_at: datetime
    # The evidence quote with the surrounding text of the message, for source inspection.
    context: str
    source_suspicious: bool
    related: list[RelatedAssertion]


class Correction(BaseModel):
    what: str | None = None
    due: date | None = None
    clear_due: bool = False
    committed_by: str | None = None
    committed_to: str | None = None


class StatusChange(BaseModel):
    status: str
