# AGENT.md — Autonomous Build Plan

## Mission

You are the implementation agent for the Personal World Model MVP.

Your objective is NOT to build a generic AI assistant.

Your objective is to create a working product that proves:
> A persistent world model can understand a person's life from passive sources plus explicit memories, represent changes over time, and proactively surface useful information.

## Required behavior

Work in small, verifiable increments. After each milestone:
- run tests
- run lint/type checks
- verify database migrations
- document decisions
- report what works and what remains

Never invent integrations or credentials. If external credentials are unavailable, build a local mock adapter and continue.

---

# Phase 0 — Product and research scaffolding

### Task 0.1
Create:
- README
- architecture diagram
- environment variable documentation
- local development instructions
- privacy/security threat model

### Task 0.2
Create a synthetic dataset representing:
- 10 people
- 5 relationships
- 10 things
- 15 calendar events
- 10 email threads
- 5 commitments
- 5 decisions
- conflicting facts
- changed facts over time

This dataset is the core evaluation fixture.

### Task 0.3
Define evaluation labels:
- confirmed
- inferred
- uncertain
- obsolete
- contradicted

Do not proceed until the fixture can be loaded and queried.

---

# Phase 1 — Domain model

Implement the canonical domain entities:

Person
Relationship
Thing
Commitment
Decision
Priority
Event
Document
Source
Assertion

Every derived assertion needs:
- source_id
- confidence
- observed_at
- valid_from
- valid_to when known
- extraction_method
- status

Implement merge/split/correction operations.

### Acceptance test
Given two emails referring to the same person, the system resolves them to one person while retaining both sources.

Given a changed phone number or changed relationship, the system preserves historical state.

---

# Phase 2 — Authentication and ingestion

Implement:
- user authentication
- Gmail OAuth read-only
- Google Calendar OAuth read-only
- connector abstraction

Requirements:
- least privilege
- encrypted token storage
- revocation support
- idempotent synchronization
- retry handling

Normalize external records into internal Source/Event records.

Do NOT immediately create facts from every message. Preserve raw/normalized source records separately from derived world-model assertions.

---

# Phase 3 — Extraction pipeline

Implement an asynchronous extraction pipeline.

For each source:
1. classify relevance
2. extract candidate entities/events
3. resolve entities
4. extract commitments
5. extract decisions
6. extract important temporal changes
7. attach provenance
8. assign confidence
9. persist derived assertions

The extraction system must be replaceable. Do not hard-code business logic to one model provider.

Add structured JSON schemas and validation.

---

# Phase 4 — Retrieval and reasoning

Implement:
- entity retrieval
- semantic retrieval
- temporal retrieval
- source retrieval
- relationship traversal

Queries should be grounded in the world model.

Every important answer should be able to provide:
- what the system believes
- confidence
- source/evidence
- correction action

Build:
- Ask Your World
- Remember this
- Correct this

---

# Phase 5 — Your World

Build the first product UI.

Home page:

## What changed
Meaningful changes since last visit.

## Needs attention
High-confidence commitments, deadlines, renewals and anomalies.

## Remembered
Confirmed user memories and decisions.

## Ask your world
Natural-language input.

Do not build a giant dashboard. The product should feel calm and useful.

---

# Phase 6 — World Brief

Create daily/weekly summaries.

Rules:
- prioritize high-confidence/high-impact items
- suppress duplicates
- suppress low-value noise
- explain why each item matters
- link to evidence
- allow dismiss/correct/remember

Measure:
- opened
- useful
- dismissed
- corrected
- acted upon

---

# Phase 7 — Commitment Radar

Detect language such as:
- I'll send...
- I'll call...
- let's meet...
- remind me...
- due by...
- registration closes...
- need to...
- promised...

Never present an uncertain commitment as fact.

UI:
> "Possible commitment detected"
> [Confirm] [Dismiss] [Edit]

After confirmation, track status.

---

# Phase 8 — Decision Memory

Detect likely decisions and their rationale.

Example:
> "We decided to keep the car until 2028 because..."

Store:
- decision
- rationale
- assumptions
- alternatives if available
- timestamp
- source

Allow:
- confirm
- correct
- supersede

Support:
> "Why did I decide X?"

and:
> "Have the reasons behind my previous decision changed?"

---

# Phase 9 — Proactive change detection

Build a temporal comparison engine.

Detect:
- changed dates
- changed prices
- changed plans
- new commitments
- approaching deadlines
- changed relationships/statuses
- decisions whose assumptions may have changed

Do NOT make recommendations unless the evidence is sufficient.

---

# Phase 10 — Customer Advocate preparation

Do not autonomously contact companies in MVP.

Detect cases such as:
- subscription price increase
- return deadline
- warranty issue
- billing discrepancy

Generate:
- issue summary
- supporting evidence
- suggested next action
- draft message

Require human approval.

Track:
- prepared
- approved
- rejected
- outcome

---

# Phase 11 — Evaluation

Create an automated evaluation suite covering:

1. Entity extraction precision/recall
2. Entity resolution
3. Temporal reasoning
4. Commitment precision
5. Decision precision
6. Source grounding
7. Hallucination rate
8. Proactive usefulness
9. Permission enforcement

Target before broad beta:
- >90% source grounding for factual answers
- >85% commitment precision on benchmark
- >85% decision precision on benchmark
- zero unauthorized actions
- clear provenance on every high-impact claim

These are engineering targets, not claims about final product performance.

---

# Phase 12 — Design-partner beta

Recruit 20–50 users.

Onboarding:
1. connect Gmail
2. connect Calendar
3. wait for initial processing
4. review first 10–20 inferred facts
5. correct/confirm
6. receive first World Brief
7. ask five suggested questions

Collect:
- usefulness
- surprise
- trust
- false positives
- missed information
- privacy concerns
- retention

The highest-priority product question:
> "Did this save you from having to remember or search for something?"

---

# Phase 13 — MVP release criteria

Do not call the MVP complete until:

### Product
- onboarding works
- first useful insight appears quickly
- user can inspect/correct memory
- World Brief works
- Ask Your World works
- commitment and decision memory work
- advocate drafts work

### Reliability
- sync retries correctly
- duplicate ingestion is safe
- failures are observable
- permissions are enforced

### Trust
- provenance exists
- inferred vs confirmed is visible
- deletion/revocation works
- no unauthorized actions

### Measurement
Events are instrumented for:
- activation
- insight usefulness
- correction
- dismissal
- query success
- retention
- agent approval

---

# Rules for autonomous implementation

1. Do not ask the founder to make trivial decisions.
2. Do ask when a decision changes product scope, privacy posture, data ownership, or core architecture.
3. Prefer reversible decisions.
4. Prefer the smallest testable implementation.
5. Never hide uncertainty.
6. Never fabricate data, credentials, users, or integration results.
7. Never send external messages without explicit approval in MVP.
8. Keep the Personal World Model independent from any single agent.
9. Keep agent permissions scoped.
10. Every new feature must answer:
   - What user problem does it solve?
   - What new world-model capability does it require?
   - Does it improve the core data flywheel?
   - Can it wait until after MVP?

## End state

A user should be able to say:

> "Connect my life."

The system should build a trustworthy initial model, show:
> "Here's what I understand about your world."

and then progressively become more useful without requiring the user to manually maintain a productivity database.
