# World Model Extraction Prompt

Extract only information supported by the source.

For each candidate assertion:
- entity
- relation
- value
- type
- confidence
- source span/reference
- observed_at
- valid_from
- valid_to if known
- whether confirmed, inferred, uncertain, obsolete, or contradicted

Never invent relationships, commitments, decisions or preferences.
When evidence is ambiguous, emit uncertain rather than guessing.
