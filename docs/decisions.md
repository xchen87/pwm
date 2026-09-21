# Decision log

Append-only. Each entry: the decision, why, and what would make us revisit it. Items marked **VERIFY** contain facts that must be checked against live vendor documentation before anyone plans around them.

## 2026-09-21 — Design review outcomes

### D1. AGENT.md is the single plan of record; build in vertical slices
**Why:** AGENT.md and TECHNICAL_BRIEF.md previously gave different build orders, beta sizes, and entity lists. The layer-by-layer order also delayed any testable user value to Phase 5–7 and evaluation to Phase 11.
**Now:** Phase 0 (fixture + eval harness) → Commitment Radar → What changed/Brief → Ask → real OAuth → phone delivery → beta. Precedence order is in CLAUDE.md.
**Revisit if:** design-partner interviews show a different first wedge than commitments.

### D2. Assertion is the core primitive; status split into three axes
**Why:** the old enum (confirmed/inferred/uncertain/obsolete/contradicted) mixed origin, user review, and temporal validity, and the extraction prompt asked the model to emit "confirmed" — contradicting "never silently turn inference into truth".
**Now:** `origin` (pipeline), `review` (user actions only), validity (derived in code); `contradicts`/`supersedes` are relations. Assertions are append-only and bitemporal.

### D3. Verified evidence quotes
**Why:** cheapest available guard against hallucination and against injected content. A candidate whose quote is not literally in the source is dropped.

### D4. Coarse, code-computed confidence
**Why:** model self-reported probabilities are uncalibrated; showing them implies precision we do not have. Calibrate against beta confirmation rates later.

### D5. Reduced entity set
**Why:** Priority has almost no passive signal; inferred relationship types are unreliable and unsettling when wrong; Document duplicated Source.
**Now:** Source, Assertion, Person, Event, Commitment, Thing, Decision. Relationship types and priorities are user-stated only.

### D6. PostgreSQL-only modular monolith; no agent runtime
**Why:** the earlier component list (event store, graph layer, vector store, temporal index, policy engine, agent runtime) is more infrastructure than an MVP with 20–50 users needs. Brief and Ask are a query plus one model call.
**Revisit if:** a measured bottleneck appears.

### D7. Funnel pipeline
**Why:** most mail is noise and calendar data is already structured. Nine model passes per message would make backfill unaffordable and slow first insight. Newest-first, 90-day initial backfill for activation in minutes.

### D8. Evaluation from Phase 0; recall and adversarial sets added
**Why:** precision-only targets reward silence, while the promise is "catches things". A small LLM-written fixture overstates quality and has no noise. Added: recall targets, noise-heavy fixture with near-miss negatives, injection suite (100% bar), founder-labelled local golden set as the honest benchmark.

### D9. Privacy posture
- Treat all source content as untrusted; models reading it get no tools.
- Store metadata + verified quotes, re-fetch bodies on demand; no mailbox mirror. **Hard to reverse — chosen deliberately.** Cost: source inspection needs a live Gmail connection.
- LLM provider is a disclosed sub-processor; source content only goes to models available with zero data retention and no training on content. **VERIFY** provider terms and per-model ZDR availability before Slice 4; some frontier models are not ZDR-eligible by default, which constrains model choice for stages that read raw mail.
- **VERIFY (Task 0.7):** Google restricted-scope requirements for `gmail.readonly` — verification steps, security assessment, unverified-app user cap, refresh-token lifetime in "Testing" status. Beta size (20–50) is set to stay under the cap.

### D10. Decision Memory (passive) and Customer Advocate are gated
**Why:** people rarely write decisions and rationale in email, so passive detection risks low recall and low frequency; Advocate is a second product. Both stay in MVP scope but are built last, only when the gates in AGENT.md open. Explicit decision capture and consumer-issue Brief items ship earlier and generate the evidence for the gates.

### D11. Onboarding review happens inline
**Why:** "review 10–20 inferred facts" is homework and contradicts the promise of no manual upkeep. Unreviewed items are confirmed or dismissed inside the Brief and Needs-attention list.

### D12. Prompt caching by construction
**Why:** extraction repeats the same long instructions for every source; caching and batching are the largest cost levers, and they fail silently when misused.
**Now:** frozen versioned prefixes longer than the model's minimum cacheable length; volatile content after the breakpoint; one model per stage; batch interface for backfill; cache-read tokens logged and asserted in tests.

### D13. Stack: Expo app + FastAPI/Postgres backend
**Why:** a phone app is required for real deployment, and early testing happens on a PC. Expo gives one TypeScript codebase for iOS, Android, and web — the PC browser/emulator build is the product itself, so nothing is rewritten for phones, and users get real store apps with push notifications. Python + Pydantic on the backend lets one set of models serve the API, the extraction schemas, and the eval harness; the app consumes a generated OpenAPI client.
**Alternatives considered:** responsive web/PWA only (weak push and store presence on iOS; does not meet the "real phone app" requirement); Flutter (good apps, but a second language and weaker web output); separate native apps (three codebases — not viable for an MVP team).
**Constraint accepted:** stay inside the Expo SDK; no custom native modules (widgets, watch, share extensions) in the MVP.
**Revisit if:** a must-have feature needs a native module Expo cannot provide.

### D14. Mobile privacy rules
Push payloads carry no personal content; OAuth through the system browser with PKCE, never a webview; Google refresh tokens stay server-side; session tokens in secure storage; no source content persisted on device.
