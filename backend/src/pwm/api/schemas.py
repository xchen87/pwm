from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, model_validator


class SourceSummary(BaseModel):
    kind: str
    sender_name: str | None
    sender_address: str | None
    subject: str
    observed_at: datetime


class CommitmentItem(BaseModel):
    id: UUID
    kind: str
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
    subject: str
    predicate: str
    extraction_method: str
    recorded_at: datetime
    # The evidence with the surrounding text of the message, for source inspection.
    context_before: str
    context_quote: str
    context_after: str
    source_suspicious: bool
    related: list[RelatedAssertion]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value.strip()


Text = Annotated[str | None, AfterValidator(_clean)]


class Correction(BaseModel):
    what: Annotated[Text, Field(min_length=1, max_length=2000)] = None
    due: date | None = None
    clear_due: bool = False
    committed_by: Annotated[Text, Field(max_length=200)] = None
    committed_to: Annotated[Text, Field(max_length=200)] = None

    @model_validator(mode="after")
    def _not_blank(self) -> "Correction":
        if self.what is not None and not self.what:
            raise ValueError("what must not be blank")
        return self


class StatusChange(BaseModel):
    status: str
