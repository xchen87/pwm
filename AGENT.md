# AGENT.md — Autonomous Build Plan

This is the **single plan of record**. TECHNICAL_BRIEF.md describes architecture; it does not define order. If the two disagree, this file wins and the brief gets fixed.

## Mission

You are the implementation agent for the Personal World Model MVP.

Your objective is NOT to build a generic AI assistant.

Your objective is to create a working product that proves:
> A persistent world model can understand a person's life from passive sources plus explicit memories, represent changes over time, and proactively surface useful information.

## Required behavior

Work in small, verifiable increments. After each slice:
- run tests
- run lint/type checks (ruff, mypy, tsc, eslint)
- verify database migrations (up and down)
- run the eval suite and record scores in `eval/results/`
- append decisions to `docs/decisions.md`
- report what works and what remains

Never invent integrations or credentials. If external credentials are unavailable, build a local mock adapter and continue.

## Why vertical slices

The product promise ("catches things before I have to remember them") must be testable early. Each slice goes all the way from source data to a screen in the app to an eval score. Do not build a layer (all entities, all connectors, all retrieval) ahead of the slice that needs it.

Every slice is developed against the synthetic fixture through the mock connector and runs on a PC: backend locally, the Expo app in a browser (`expo start --web`) and in an Android emulator / iOS simulator where available. The same app code ships to phones in Slice 5 — there is no separate "mock UI".

## Repository layout

```text
backend/     FastAPI service, domain model, pipeline, connectors, migrations
app/         Expo app (iOS, Android, web) — TypeScript
eval/        eval harness, metrics, results history
fixtures/    synthetic dataset + adversarial set (no real user data, ever)
prompts/     versioned, frozen prompt prefixes
docs/        architecture, threat model, decisions, env vars
```

---

# Phase 0 — Foundations

### Task 0.1 — Scaffolding and documents
Create:
- backend and app skeletons with lint, type check, and test commands
- `docs/architecture.md` (diagram)
- `docs/env.md` (environment variables)
- `docs/local-dev.md`
- `docs/threat-model.md` — must cover, at minimum: prompt injection via email content, third-party (correspondent) data, LLM sub-processor exposure and retention, OAuth token theft, device loss, push-notification leakage, deletion guarantees
- `docs/decisions.md` (already seeded)

### Task 0.2 — Synthetic fixture
Create a synthetic dataset representing one user's world:
- 10 people (with alias/duplicate-address cases)
- 10 things
- 15 calendar events
- 10 meaningful email threads
- **at least 60 noise messages** (newsletters, receipts, notifications, automated mail) — real inboxes are mostly noise, and the fixture must be too
- 5 commitments made by the user, 5 made *to* the user
- 5 decisions
- conflicting facts
- changed facts over time (moved dates, changed phone number, changed price)
- near-miss negatives: text that looks like a commitment or decision but is not ("I'd love to send you something someday", quoted text from someone else, hypotheticals)

Every expected assertion is labelled with its supporting quote.

### Task 0.3 — Adversarial fixture
At least 10 messages attempting prompt injection ("ignore previous instructions", fake commitments addressed to the assistant, fake system text, hidden HTML text, instructions to mark facts confirmed). Expected output for every one: **zero assertions derived from the injected instructions, and no state change.**

### Task 0.4 — Evaluation labels
Expected assertions are labelled on three independent axes (see TECHNICAL_BRIEF §4):
- `origin`: user_stated | source_explicit | inferred
- `review`: always `unreviewed` for pipeline output
- expected validity at a given as-of date: current | superseded | expired

Plus relation labels between assertions: `supersedes`, `contradicts`.

### Task 0.5 — Eval harness (now, not later)
Build `eval/` so that one command runs the pipeline on the fixture and reports:
1. commitment **precision and recall**
2. entity extraction precision/recall and entity resolution accuracy
3. temporal correctness (as-of queries)
4. quote-verification pass rate
5. noise rejection rate (fraction of noise messages that reach the LLM extractor; fraction producing assertions)
6. injection suite: must be 100% clean
7. cost per 100 sources and cache hit rate

Before extraction exists, the harness runs against a trivial baseline extractor and reports zeros. That is the point: every later change has a before/after.

The synthetic fixture is a **regression suite, not the benchmark**. Synthetic text written by an LLM is easy for an LLM to extract from. The honest benchmark is Task 0.6.

### Task 0.6 — Founder golden set (local only)
Provide a tool that lets the founder label ~200 threads from their own inbox locally. This set is gitignored, never leaves the machine except through the same LLM path as production, and its scores (not its content) are recorded. If no real mailbox is available, skip and say so — do not fabricate one.

### Task 0.7 — Start Google OAuth verification
`gmail.readonly` is a Google *restricted* scope. Record in `docs/decisions.md` the verified current requirements (verification, security assessment, user cap for unverified apps, refresh-token lifetime in "Testing" publishing status) — check Google's live documentation, do not rely on memory. This has a long lead time; it starts now and gates Slice 6, not Slice 4.

Do not proceed until the fixture loads, the harness runs end to end, and the baseline scores are committed.

---

# Slice 1 — Commitment Radar, end to end

**User problem:** "I said I'd do something, or someone promised me something, and nobody is tracking it."

### Domain core (only what this slice needs)
Implement: `Source`, `Assertion`, `Person`, `Event`, `Commitment`. `Thing` and `Decision` arrive with the slices that need them.

`Assertion` is the core primitive (TECHNICAL_BRIEF §3–4). It is append-only and carries:
- source_id, evidence_quote (verbatim), extraction_method, prompt_version
- origin, review, confidence (high | medium | low)
- observed_at, valid_from, valid_to, recorded_at
- superseded_by

Implement merge / split / correct for people. Corrections are new user_stated assertions that supersede, never in-place edits.

### Pipeline — a funnel, not nine LLM passes
1. **Deterministic prefilter** — Gmail categories, `List-Unsubscribe`, noreply senders, bulk headers. No LLM.
2. **Thread assembly** — strip quoted replies and signatures; one unit of work per thread, not per message.
3. **Triage** — one cheap-model call: is this thread worth extracting from?
4. **Extraction** — one structured-output call returning candidate people, events, commitments, each with a verbatim quote.
5. **Quote verification (code)** — the quote must be a substring of the normalized source. If not, drop the candidate and log it.
6. **Entity resolution (code first)** — deterministic matching on address/name/alias; LLM only for ambiguous cases.
7. **Temporal reconciliation (code)** — compare with existing assertions; write `supersedes` / `contradicts` relations.
8. **Confidence assignment (code)** — from origin, evidence count, and extractor agreement. Never the model's self-reported number.
9. **Persist** with full provenance; audit-log the LLM calls.

Calendar events skip steps 3–4: they are already structured.

The pipeline is asynchronous on a Postgres jobs table (`SELECT … FOR UPDATE SKIP LOCKED`). Jobs are idempotent by (source_id, prompt_version).

### LLM boundary
- `Extractor` and `Reasoner` are narrow interfaces. Business logic never imports a provider SDK.
- Each stage uses one model and one frozen prompt prefix (system prompt + JSON schema + few-shot examples from the fixture), long enough to exceed the chosen model's minimum cacheable prefix. The cache breakpoint sits at the end of that prefix; source text and dates come after it.
- Log `cache_read_input_tokens` per call. A test fails if repeated calls with the same prefix report zero cache reads.
- Source text is wrapped and labelled as untrusted data. The extraction model has no tools.

### App (Expo)
One screen: **Needs attention**.
> "Possible commitment detected" — quote, who, what, when
> [Confirm] [Dismiss] [Edit]

Tapping an item opens **source inspection**: the evidence quote in context, origin, confidence, and when it was observed. Confirm/Dismiss/Edit write user review state; nothing else can.

After confirmation, track status (open, done, overdue, cancelled).

### Acceptance
- Two emails from different addresses of the same person resolve to one person and retain both sources.
- A changed phone number or moved date preserves history; as-of queries return the old value for old dates.
- Every stored assertion has a verified quote.
- Injection suite 100% clean.
- Commitment precision **and recall** reported on fixture (and golden set if available). Never present an unreviewed commitment as fact.
- The screen runs in a browser and in an emulator from the same code.

---

# Slice 2 — What changed + World Brief

**User problem:** "Things moved and I didn't notice."

Add `Thing`. Build the temporal comparison engine (code, over assertions):
- changed dates, prices, plans
- new commitments, approaching deadlines
- changed statuses
- consumer issues (price increase, return window, renewal) as a **Brief item type** — detection and evidence only, no drafts (see Gated slices)

World Brief (daily/weekly), generated from a query over assertions plus one LLM call:
- prioritize high-confidence / high-impact items
- suppress duplicates and low-value noise
- explain why each item matters, link to evidence
- unreviewed items appear inline with [Confirm] [Dismiss] — this replaces any up-front "review 20 facts" onboarding step
- allow dismiss / correct / remember
- do NOT make recommendations unless the evidence is sufficient

App: Home with **What changed**, **Needs attention**, **Remembered**. Calm, not a dashboard.

Delivery: a `Notifier` interface with a mock implementation (logged + in-app inbox) on PC. Notification payloads contain **no personal content** — a generic "Your World Brief is ready" and a deep link. Real push arrives in Slice 5 behind the same interface.

Measure: opened, useful, dismissed, corrected, acted upon.

---

# Slice 3 — Ask Your World + explicit memory

Implement retrieval over the world model, all in Postgres:
- entity retrieval, temporal (as-of) retrieval, source retrieval
- semantic retrieval (pgvector) over verified quotes and user memories
- relationship traversal (recursive CTEs) over interaction facts

Every answer provides: what the system believes, confidence, evidence quote, and a correction action. If the model cannot ground an answer, it says so.

Build:
- Ask Your World
- Remember this (user_stated assertions, including explicit decisions and priorities)
- Correct this

Add to eval: source-grounding rate and hallucination rate for answers; injection suite extended to retrieved content.

---

# Slice 4 — Real accounts and real data

Implement:
- user authentication (sessions for web, tokens in secure device storage for phones)
- Gmail OAuth read-only, Google Calendar OAuth read-only, behind the existing connector abstraction
- OAuth runs **server-side** through the system browser with PKCE and a deep link back to the app. Never an embedded webview. Google refresh tokens live only on the server, encrypted; the phone never holds them.
- revocation, disconnect, and full deletion with cascade (source → assertions → embeddings → brief items), verified by test
- idempotent sync, retry with backoff, observable failures
- **newest-first backfill** limited to 90 days initially, so the first useful insight appears within minutes; older history is optional and uses the Batch API

Storage posture: store normalized metadata and verified quotes (encrypted at rest); re-fetch full bodies from Gmail on demand for source inspection. Do not mirror mailboxes.

Do NOT create facts from every message. Raw/normalized source records stay separate from derived assertions.

---

# Slice 5 — Phone delivery

The app has been Expo since Slice 1; this slice makes it a real installed app.
- EAS builds for iOS and Android; TestFlight and Play internal testing
- real push via Expo Notifications behind `Notifier`; generic payloads only
- deep links (brief item, OAuth return)
- secure token storage (expo-secure-store), optional biometric app lock
- no source content cached on device beyond the current session
- device QA: small screens, offline/poor network, background → foreground, notification tap-through
- web build deployed from the same code

Anything that would require a custom native module is out of MVP scope.

---

# Slice 6 — Design-partner beta

Recruit 20–50 users (must stay under Google's unverified-app user cap until verification completes; see Task 0.7).

Onboarding:
1. install app
2. connect Gmail
3. connect Calendar
4. first items appear within minutes (newest-first)
5. receive first World Brief, confirming/correcting inline
6. ask five suggested questions

Collect: usefulness, surprise, trust, false positives, **missed information**, privacy concerns, retention.

The highest-priority product question:
> "Did this save you from having to remember or search for something?"

Also ask every partner the two gating questions below.

---

# Gated slices

These are in MVP scope but are **not built until the gate opens**. The founder opens a gate; the agent does not.

### Slice 7 — Passive Decision Memory
*Gate:* beta evidence that decisions appear in partners' email/calendar often enough to detect (from golden-set labelling and partner interviews), and explicit decision capture (Slice 3) is being used.

Detect likely decisions and rationale. Store decision, rationale, assumptions, alternatives, timestamp, source. Allow confirm / correct / supersede. Support "Why did I decide X?" and "Have the reasons behind my previous decision changed?"

### Slice 8 — Customer Advocate drafts
*Gate:* consumer-issue Brief items (Slice 2) are marked useful by partners, and partners ask for help acting on them.

Generate issue summary, supporting evidence, suggested next action, draft message. Require human approval. Never contact companies autonomously. Track prepared / approved / rejected / outcome.

---

# MVP release criteria

Do not call the MVP complete until:

### Product
- onboarding works on a real phone
- first useful insight appears within minutes
- user can inspect/correct memory
- World Brief works, including push delivery
- Ask Your World works
- Commitment Radar works
- gated slices are either shipped or explicitly deferred by the founder

### Reliability
- sync retries correctly
- duplicate ingestion is safe
- failures are observable
- permissions are enforced

### Trust
- every stored assertion has a verified quote
- inferred vs confirmed is visible
- deletion/revocation cascades and is tested
- injection suite 100% clean
- no unauthorized actions

### Evaluation targets (engineering targets, not claims about final product performance)
- >90% source grounding for factual answers
- >85% commitment precision **and** >70% commitment recall on the benchmark (recall target to be revised upward after the first golden-set run)
- zero unauthorized actions
- zero assertions from the injection suite

### Measurement
Events are instrumented for: activation, insight usefulness, correction, dismissal, query success, retention, notification open, agent approval.

---

# Rules for autonomous implementation

1. Do not ask the founder to make trivial decisions.
2. Do ask when a decision changes product scope, privacy posture, data ownership, or core architecture.
3. Prefer reversible decisions.
4. Prefer the smallest testable implementation.
5. Never hide uncertainty.
6. Never fabricate data, credentials, users, or integration results.
7. Never send external messages without explicit approval in MVP.
8. Keep the Personal World Model independent from any single agent or model provider.
9. Keep agent permissions scoped. Models that read source content get no tools.
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
