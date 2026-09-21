"""The shape retrieval works on. Built from database rows in the API and from pipeline
output in the eval harness, so both exercise the same retrieval and answering code."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class Fact(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    subject: str
    predicate: str
    value: str
    evidence_quote: str
    # Words from around the evidence that help find it: message subject and sender name.
    context_words: str = ""
    source_label: str = ""
    observed_at: datetime
    is_fact: bool = False
    confidence: str = "medium"
    superseded: bool = False
    previous_value: str | None = None
    commitment_type: str | None = None
    direction: str | None = None
    committed_by: str | None = None
    committed_to: str | None = None
    due: date | None = None
    status: str | None = None
