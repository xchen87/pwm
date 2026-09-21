# Personal World Model — Technical Brief

This document describes architecture and the data model. **Build order and acceptance criteria live in AGENT.md**, which is the single plan of record.

## 1. Product thesis

Build a user-controlled Personal World Model (PWM): a persistent, temporal representation of a person's meaningful world — people, things, commitments, decisions, events, and the evidence behind them.

The product is not a generic chatbot or task manager. The model is the durable context substrate. Product experiences are queries and workflows on top of it.

Core promise:
> Connect your life. We'll remember what matters, tell you what changed, and catch things before they become problems.

## 2. Product architecture

```text
Sources (untrusted input)
  ├── Gmail (read-only)
  ├── Google Calendar (read-only)
  └── Explicit user capture
        ↓
Connectors → immutable Source records (metadata + verified quotes; bodies re-fetched on demand)
        ↓
Funnel pipeline (Postgres jobs queue)
  1. deterministic prefilter          (code)
  2. thread assembly, quote stripping (code)
  3. triage                           (cheap model)
  4. structured extraction            (model, no tools)
  5. quote verification               (code — drop if quote not in source)
  6. entity resolution                (code first, model for ambiguity)
  7. temporal reconciliation          (code — supersedes / contradicts)
  8. confidence assignment            (code)
        ↓
Personal World Model  =  append-only Assertions about thin entities
        ↓
Retrieval (SQL, as-of queries, pgvector, recursive CTEs)
        ↓
Experiences (FastAPI)
  ├── Commitment Radar
  ├── What changed / World Brief
  ├── Ask Your World
  ├── Remember / Correct
  └── Source inspection
        ↓
Expo app — one TypeScript codebase → iOS, Android, web
        ↓
User review / approval (the only path to "confirmed")
```

There is no agent runtime in the MVP. World Brief is a query plus one model call; Ask Your World is retrieval plus one model call. An agent runtime is a post-MVP concern (§12).

## 3. Core data concepts

### Assertion — the core primitive
A single claim about the world, with its evidence. Entities are thin identities; nearly everything known about them is a set of assertions. Assertions are append-only: change is a new assertion that supersedes an old one.

Fields:
- subject entity, predicate, value
- `source_id`, `evidence_quote` (verbatim, machine-verified against the source)
- `extraction_method`, `prompt_version`, model id
- `origin`, `review`, `confidence` (§4)
- `valid_from`, `valid_to`, `observed_at`, `recorded_at` (§5)
- `superseded_by`
- relations to other assertions: `supersedes`, `contradicts`

### MVP entities
| Entity | Notes |
|---|---|
| Source | Immutable record of an email thread message, calendar event, or user capture. Covers what earlier drafts called "Document". |
| Person | Identity, aliases/addresses, interaction history. Supports merge / split / correct. |
| Event | Timestamped event with participants, location, source. |
| Commitment | Who committed to what, to whom, deadline, status. |
| Thing | Physical/digital asset or subscription: owner, purchase, price, renewal, warranty. |
| Decision | Decision, rationale, assumptions, alternatives, outcome. Explicit capture is core; passive detection is a gated slice. |

### Deliberately not first-class in the MVP
- **Relationship** — the system infers only *interaction facts* (frequency, recency, shared events, open commitments). Relationship *types* ("sister", "landlord") exist only as user-stated assertions. Guessing them from email is unreliable and unsettling when wrong.
- **Priority** — there is almost no passive signal for priorities in Gmail/Calendar. Priorities exist only as user-stated assertions via "Remember this".
- **Preference, Outcome** — post-MVP.

## 4. Epistemic model

Earlier drafts used one status enum (confirmed / inferred / uncertain / obsolete / contradicted). That conflated three independent questions, and asked the extraction model to answer ones it cannot. They are now separate:

| Axis | Values | Who sets it |
|---|---|---|
| `origin` — how do we know? | `user_stated`, `source_explicit` (the source says it outright), `inferred` (derived by reasoning) | pipeline |
| `review` — has the user weighed in? | `unreviewed`, `confirmed`, `rejected`, `corrected` | **user actions only** |
| validity — is it still true? | derived from `valid_to`, `superseded_by`, and as-of date | code |

`contradicts` is a relation between two assertions, discovered by reconciliation — not a label the extractor applies to one source in isolation.

**Confidence** is coarse — `high | medium | low` — and computed in code from origin, number of independent sources, recency, and extractor agreement. Model self-reported probabilities are uncalibrated and are never stored or shown. Once the beta produces confirm/dismiss data, confidence is calibrated against actual confirmation rates.

UI rule: `review = confirmed` and `origin = user_stated` render as fact; everything else renders as "possible …" with the evidence one tap away.

## 5. Temporal model

Bitemporal, so the system can answer both "what was true then?" and "what did we believe then?":
- `valid_from` / `valid_to` — when the claim holds in the world
- `observed_at` — timestamp of the source
- `recorded_at` — when the system wrote the assertion
- `superseded_by` — replaced by a newer assertion

Change detection is a comparison over assertions, in code. Example: a moved appointment produces a new Event-time assertion superseding the old one; "what changed" reports the pair with both quotes.

## 6. Trust model

Three action levels:
1. Observe — detect and explain.
2. Prepare — draft an action and request approval.
3. Act — execute only within explicit user-granted scope. **Not in MVP.**

Never silently convert an inference into a fact. Only a user action writes `review`.

### Untrusted content
Every email and calendar description is attacker-controllable text. Defenses, in layers:
- source text is delimited and labelled as data in every prompt; prompts instruct the model to ignore instructions inside it
- models that read source content have **no tools** and produce only schema-validated JSON
- quote verification drops anything the source does not literally support
- pipeline output can never set `review`, trigger an action, or change permissions
- an adversarial fixture runs in the eval suite on every change; the pass bar is 100%

### Third parties and sub-processors
- Correspondents did not consent. Store the minimum: metadata and verified quotes, not mailbox mirrors. Bodies are re-fetched on demand for source inspection.
- The LLM provider is a disclosed sub-processor. Source content is sent only to models available under a zero-data-retention arrangement, with no training on user content. Model choice for any stage that reads raw source text is constrained by this; record the verified provider terms in `docs/decisions.md` before Slice 4.
- Google API Limited Use requirements apply to all Gmail-derived data.

### Google OAuth constraints
`gmail.readonly` is a restricted scope: verification and a security assessment have long lead times, unverified apps have a user cap, and "Testing" publishing status shortens refresh-token lifetime. Verified specifics go in `docs/decisions.md` (AGENT.md Task 0.7). Beta size is planned around the cap.

## 7. MVP

### Integrations
- Gmail, read-only
- Google Calendar, read-only
- Manual capture

### Experiences (in build order)
1. **Commitment Radar** — detect promises/deadlines in both directions and ask for confirmation.
2. **Your World / What changed** — calm home view of meaningful changes and pending issues.
3. **World Brief** — daily/weekly summary, delivered in-app and by push; unreviewed items confirmed inline.
4. **Ask Your World** — natural-language queries, source-grounded.
5. **Memory** — "Remember this" and "Correct this", including explicit decisions and priorities.
6. **Source inspection** — the evidence quote, in context, for any claim.

Gated (AGENT.md): passive **Decision Memory**; **Customer Advocate** drafts. Until ungated, consumer issues surface as World Brief items only.

### Clients
iOS, Android, and web from one Expo codebase. The phone app is the primary surface; push is the primary delivery channel for the Brief.

## 8. MVP non-goals

- autonomous purchasing, financial transactions
- health integrations
- social-media ingestion, WhatsApp/iMessage
- agent marketplace, family suite
- generic chatbot features unrelated to the world model
- platform-specific native modules: widgets, watch apps, share extensions, on-device ML, background mail processing on device
- offline mode beyond graceful degradation
- inferred relationship types, inferred priorities

## 9. Technical direction

A modular monolith. Boundaries are Python modules with explicit interfaces, not services.

| Concern | MVP implementation |
|---|---|
| API | FastAPI; OpenAPI schema is the contract |
| Domain + validation | Pydantic v2 models — shared by API, extraction schemas, and eval |
| Source of truth | PostgreSQL (SQLAlchemy 2, Alembic) |
| Queue | Postgres jobs table, `FOR UPDATE SKIP LOCKED`, idempotency keys |
| Semantic retrieval | pgvector |
| Text search | Postgres full-text search |
| Relationship traversal | recursive CTEs |
| Temporal index | btree/GiST indexes on validity ranges |
| Audit / provenance | append-only tables |
| Permissions | a policy module checked at the API layer |
| LLM access | `Extractor` and `Reasoner` interfaces; provider SDKs imported only inside adapters |
| App | Expo (React Native + TypeScript), Expo Router, react-native-web |
| App ↔ API | TypeScript client generated from OpenAPI |
| Push | `Notifier` interface → Expo Notifications; mock on PC |
| Auth on device | system-browser OAuth (PKCE) + deep link; tokens in expo-secure-store; Google tokens server-side only |

No graph database, separate vector store, event-streaming system, or agent framework until a measured need appears. "Provider-agnostic" is delivered by the narrow interfaces **plus the eval suite** — a provider swap is safe only because scores show whether it regressed.

### Why Expo
The phone app is a must-have, and the first testing happens on a PC. Expo runs the *same* screens in a browser, in simulators/emulators, and on devices, and produces store builds through EAS. What is tested on the PC is the product, not a throwaway mock. Constraint accepted in exchange: stay inside the Expo SDK — no custom native modules in the MVP.

### Mobile-specific privacy rules
- Push payloads carry no personal content: generic title + deep link.
- Session tokens in secure storage; Google refresh tokens never reach the device.
- No source content persisted on device beyond the session; optional biometric lock.
- OAuth only through the system browser — never an embedded webview.

### LLM cost and caching
- The funnel exists so that most sources never reach a model and almost none reach the expensive one.
- Each model stage has a **frozen, versioned prompt prefix**: system prompt + JSON schema + few-shot examples drawn from the fixture. The prefix must exceed the minimum cacheable length of the model used for that stage (model-dependent; verify for the chosen model — a short prefix silently fails to cache).
- The cache breakpoint sits at the end of the prefix. Source text, the current date, user identifiers, and anything else that varies come **after** it. Schemas are serialized deterministically.
- One model per stage: caches are model-scoped.
- Steady-state sync uses the default short cache TTL; bursty work uses the longer TTL; historical backfill uses the provider's batch interface together with caching.
- Every call logs model, prompt version, input/output tokens, and cache-read tokens to the audit table. The eval harness reports cost per 100 sources and cache hit rate; a test fails if repeated same-prefix calls show zero cache reads.
- Ask Your World caches the stable part of its context (instructions + answer schema); retrieved evidence and the question come after the breakpoint.

## 10. Critical engineering principles

- User-owned data and exportability.
- Least-privilege OAuth scopes.
- Encryption in transit and at rest; application-level encryption for OAuth tokens and stored quotes.
- Explicit consent and revocation; deletion cascades through all derived data and is tested.
- Verified source quote for every extracted fact.
- Idempotent ingestion.
- Deterministic entity IDs and merge/split operations.
- Human confirmation for uncertain/high-impact items.
- Evaluation from day one; no pipeline or prompt change without before/after scores.
- Observability for every model call and every user-visible decision.
- No model-training use of user content.
- Real user data never enters the repository.

## 11. Evaluation

### Offline (eval harness, every change)
- commitment precision **and recall**
- entity extraction P/R; entity resolution accuracy
- temporal correctness (as-of queries)
- quote-verification pass rate
- noise rejection (how much noise reaches a model; how much yields assertions)
- answer grounding and hallucination rate
- injection suite (must be 100% clean)
- permission enforcement
- cost per 100 sources; cache hit rate

Datasets: the synthetic fixture (noise-heavy, with near-miss negatives) as a **regression suite**; the adversarial fixture; and a locally held, founder-labelled real-inbox golden set as the **honest benchmark**. Synthetic scores alone are never quoted as product quality.

Precision without recall rewards a system that stays silent; the product promise is about catching things, so both are targeted.

### Online (beta)
- **Activation** — share of connected users with a useful insight within the first session (target: minutes, not 24 hours).
- **Proactive value** — share of Brief items marked useful; this cannot be measured offline.
- **Missed information** — things partners report the system should have caught.
- **Commitment / memory precision** — confirmation rates; these also calibrate confidence.
- **Trust** — corrections, dismissals, revocations, unexplained items.
- **Retention** and notification open rate.

## 12. Long-term platform

After the MVP proves the model, the PWM becomes a substrate for scoped agents (Life Radar, Customer Advocate, Ownership, Relationship, Decision, Family, Financial/Admin, third-party agents with scoped permissions). That is when an agent runtime, a policy engine, and level-3 "Act" permissions are designed — against real usage, not in advance.

The moat is not the LLM. It is the durable, user-controlled, temporal world model plus trust, provenance, permissions, and action history.
