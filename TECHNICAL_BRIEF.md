# Personal World Model — Technical Brief

## 1. Product thesis

Build a user-controlled Personal World Model (PWM): a persistent, temporal representation of a person's meaningful world—people, relationships, things, commitments, decisions, priorities, events, documents, preferences, and outcomes.

The product is not a generic chatbot or task manager. The model is the durable context substrate. Specialized agents operate on top of it.

Core promise:
> Connect your life. We'll remember what matters, tell you what changed, and catch things before they become problems.

## 2. Product architecture

```text
Sources
  ├── Gmail
  ├── Calendar
  └── Explicit user capture
        ↓
Ingestion + normalization
        ↓
Entity / event extraction
        ↓
Entity resolution + temporal reasoning
        ↓
Personal World Model
        ├── People / relationships
        ├── Things / ownership
        ├── Commitments
        ├── Decisions + rationale
        ├── Priorities / goals
        ├── Events
        └── Documents / provenance
        ↓
Reasoning + retrieval layer
        ↓
Agent runtime
  ├── World Brief
  ├── Ask Your World
  ├── Customer Advocate
  ├── Ownership
  ├── Relationship
  └── Decision / Memory
        ↓
User approval / action
```

## 3. Core data concepts

### Person
Identity, aliases, relationships, interaction history, importance, preferences, provenance.

### Relationship
Typed relationship between people/entities, confidence, history, last interaction, commitments.

### Thing
Physical/digital asset, owner, purchase, value, warranty, maintenance, documents, lifecycle state.

### Commitment
Who committed to what, source, deadline, status, confidence, dependencies.

### Decision
Decision, date, alternatives, rationale, assumptions, expected outcome, actual outcome, source.

### Priority
User objective, importance, horizon, constraints, and evidence.

### Event
Timestamped event with participants, entities, location, source and consequences.

### Provenance
Every extracted or inferred fact should retain source, timestamp, confidence and extraction path. Important facts must be inspectable and correctable.

## 4. Temporal model

The PWM must model change, not just facts.

Represent:
- valid_from / valid_to
- observed_at
- created_at
- supersedes
- contradicts
- confidence

Example:
A car can have multiple owners, insurance policies, repairs and decisions over time. A decision can become obsolete when its assumptions change.

## 5. Trust model

Three action levels:
1. Observe — detect and explain.
2. Prepare — draft an action and request approval.
3. Act — execute only within explicit user-granted scope.

Never silently convert an inference into a fact. UI must distinguish confirmed, inferred, and uncertain information.

## 6. MVP

### Initial integrations
- Gmail, read-only
- Google Calendar, read-only
- Manual capture

### MVP experiences
1. **Your World** — concise view of meaningful changes and pending issues.
2. **World Brief** — daily/weekly summary of what changed.
3. **Ask Your World** — natural-language queries over the model.
4. **Memory** — explicit “remember this” and correction.
5. **Commitment Radar** — detect promises/deadlines and ask for confirmation.
6. **Decision Memory** — detect likely decisions/rationale and allow confirmation.
7. **Source inspection** — show why the system believes something.
8. **Basic Customer Advocate preparation** — identify a consumer issue and prepare a draft action; no autonomous external action in MVP.

## 7. MVP non-goals

Do not build initially:
- autonomous purchasing
- financial transactions
- health integrations
- social-media ingestion
- WhatsApp/iMessage integration
- broad agent marketplace
- full family-management suite
- complex mobile-native experience
- generic chatbot features unrelated to the world model

## 8. Technical direction

Use a modular architecture so the underlying model is provider-agnostic.

Suggested components:
- API/service layer
- OAuth integration service
- ingestion queue
- normalized event store
- relational source of truth for entities and permissions
- graph-oriented relationship layer where useful
- vector/semantic retrieval for unstructured source content
- temporal/event index
- LLM extraction + reasoning workers
- policy/permission engine
- agent runtime
- audit/provenance store

Do not prematurely optimize for a particular graph database. Establish a clean domain model and interfaces first.

## 9. Critical engineering principles

- User-owned data and exportability.
- Least-privilege OAuth scopes.
- Encryption in transit and at rest.
- Explicit consent and revocation.
- Source provenance for extracted facts.
- Idempotent ingestion.
- Deterministic entity IDs and merge/split operations.
- Human confirmation for uncertain/high-impact actions.
- Evaluation datasets for extraction, entity resolution, temporal reasoning and proactive usefulness.
- Observability for every agent action.
- No model-training use of user content without explicit product policy and consent.

## 10. Core evaluation metrics

### World Coverage
Percentage of meaningful sampled facts/events correctly represented.

### Memory Precision
Percentage of surfaced memories judged useful/correct.

### Commitment Precision
Percentage of detected commitments that users confirm as real.

### Decision Precision
Percentage of inferred decisions that users confirm.

### Proactive Value
Percentage of proactive alerts that users mark useful.

### Trust
Rate of corrections, dismissals, permission revocations and unexplained actions.

### Activation
Percentage of connected users who receive at least one useful insight within 24 hours.

## 11. Recommended implementation sequence

Phase 0 — Research
- 30 user interviews
- identify recurring “I forgot / I had to search / I wish someone handled this” moments
- recruit 20 design partners

Phase 1 — Foundation
- auth
- Gmail/Calendar OAuth
- normalized event model
- provenance
- entity extraction
- entity resolution
- temporal state

Phase 2 — First magic
- Your World
- World Brief
- Ask Your World
- explicit memory
- correction UX

Phase 3 — Intelligence
- commitment detection
- decision detection
- proactive change detection
- confidence and source inspection

Phase 4 — Action
- customer-advocate preparation
- approval workflow
- action audit trail

Phase 5 — Beta
- 50–100 users
- measure usefulness, trust, retention
- fix false positives before expanding scope

## 12. Long-term agent platform

The PWM becomes a platform for:
- Life Radar Agent
- Customer Advocate Agent
- Ownership Agent
- Relationship Agent
- Decision Agent
- Family Agent
- Financial/Admin Agent
- third-party agents with scoped permissions

The moat is not the LLM. It is the durable, user-controlled, temporal world model plus trust, provenance, permissions, and action history.
