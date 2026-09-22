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

## 2026-09-21 — Phase 0

### D15. Google restricted-scope facts, verified (resolves the Task 0.7 VERIFY in D9)
Checked against Google's documentation on 2026-09-21:
- **7-day refresh tokens in Testing.** "A Google Cloud Platform project with an OAuth consent screen configured for an external user type and a publishing status of 'Testing' is issued a refresh token expiring in 7 days" — unless only name/email/profile scopes are requested. (developers.google.com/identity/protocols/oauth2)
- **100 refresh tokens** per Google Account per OAuth client ID; the oldest is invalidated silently beyond that. (same page)
- **Unverified-app cap:** "100 new users in total, after the app presents the unverified app screen." (support.google.com/cloud/answer/7454865)
- **Annual security assessment:** "Applications requesting access to restricted scopes must undergo an annual security assessment", using the App Defense Alliance CASA framework, as "the final step of the restricted scopes review process"; "All applications must be revalidated every year." (support.google.com/cloud/answer/13465431)
- **Limited Use:** use limited to "providing or improving user-facing features that are prominent in the requesting application's user interface"; humans may read user data only with "the user's affirmative agreement to view specific messages" or for security/legal reasons. (developers.google.com/terms/api-services-user-data-policy)

Caveat: these passages were retrieved through an automated page reader, so wording may differ slightly from the live pages; re-read the originals before relying on them in a legal or compliance document. That switching to "In production" status lifts the 7-day expiry is our reading of the first quote, not a separate statement by Google.

**Not found in those pages:** assessment cost, and explicit language on AI/ML training. Treat both as unknown, not as permitted or free. Our own rule (no training on user content) stands regardless.

**Consequences:**
- A beta in "Testing" status would force every partner to reconnect Gmail weekly. The beta therefore needs the app in "In production" publishing status, which means starting brand + restricted-scope verification well before Slice 6. **Founder action: create the Google Cloud project and begin verification now**; the agent cannot do this.
- Until verified, total new users are capped at 100, so the 20–50 partner target fits, with little headroom for churned testers.
- "No human reads mail" is a policy requirement, not only our preference: support and debugging tools must work from IDs and metadata.

### D16. Tooling: uv, root pyproject, Expo SDK 57
- `uv` manages Python 3.12 and the virtualenv (the dev machine ships Python 3.10). One `pyproject.toml` at the repo root packages both `backend/src/pwm` and `eval/pwm_eval`, so the eval harness imports the same models the API uses.
- Local Postgres is `pgvector/pgvector:pg16` via `docker-compose.yml` on port 5433.
- App scaffolded with Expo SDK 57 / React Native 0.86 / TypeScript 6. The template's bundled `.claude/` plugin settings, `AGENTS.md`, and MIT `LICENSE` were removed from `app/` (the licence applied to the template, and keeping it would have implied the app itself is MIT-licensed).
- `openapi-typescript` requires TypeScript 5 as a peer and the app uses 6, so it is run through `npx` (`npm run gen:api`) rather than installed as a dependency.

### D17. Eval grading is mechanical
Candidates are matched to gold by source, kind, and evidence-quote overlap (≥ 0.6 of the shorter quote's tokens) — no model grades a model. Precision is reported as n/a, not 1.0, when a system predicts nothing. An oracle system must score 1.00 everywhere and a deliberately gullible system must fail the injection suite; both are tests, so the metrics themselves are under test.
**Known limit:** quote overlap checks *where* a fact was found, not whether `value` was normalised correctly. Commitment `direction` and `due` are scored separately; value-level scoring for facts arrives with as-of queries in Slice 1–2.

### D18. Commitments have a type
`promise` (someone said they will do something) and `deadline` (a date by which the user must act: "registration closes", "due by"). AGENT.md's Commitment Radar language covers both and they need different UI wording, so the distinction is in the schema and prompt from the start.

## 2026-09-21 — Slice 1

### D19. The funnel is a pure function; persistence wraps it
`run_pipeline(sources, user, triager, extractor)` takes records in and returns a reconciled world. The eval harness and production run the same function; the database layer (`pipeline/store.py`) only ingests, caches model-stage results, and writes what the function returns. **Why:** an eval that exercises different code from production measures nothing.
**Cost:** the funnel currently reprocesses all of a user's sources per job. Model calls are never repeated (D20), so this costs CPU, not money. Revisit with incremental processing when a real mailbox makes it slow.

### D20. Model-stage results are cached per (source, stage, prompt version)
`stage_results` stores each triage and extraction output. Reprocessing, retries, and new reconciliation rules never re-pay for a call; bumping the prompt version re-extracts deliberately. A test asserts the extractor is not called twice for the same source.

### D21. Evidence is verified against the *visible* text
Quoted replies, forwarded blocks, and hidden HTML are removed before extraction and before quote verification. A forged "On … you wrote: > I agree to pay" cannot become the user's commitment even if a model is fooled, because the quote is not in what the sender actually wrote. Signatures are kept: they carry real facts (phone numbers).

### D22. Who becomes a Person, and when addresses merge
A person is created only for a direct relationship: they wrote to the user personally, the user wrote to them, or they share a calendar event. List traffic and bulk senders do not create people.
Two addresses merge only when the display names are compatible **and** the new address identifies itself with the known person's surname in the message. Nothing ever merges into the user; an address using the user's display name is flagged suspicious. Inferred links are stored as `link = inferred`; user merges/splits are `link = user` and code never overrides them.
**Residual risk:** an attacker who knows a contact's full name can self-identify as them. The link is visibly inferred and splittable, and their claims still arrive as "possible". An LLM tie-breaker for ambiguous cases is deferred until real data shows the rules are insufficient.

### D23. Reconciliation rules
Same matter = same kind and predicate, and similar subject (for commitments: same type, same committed party, similar act). A differing later statement from the **same thread or sender** supersedes; a disagreement between **independent sources** is a contradiction, both stay current, and the app says "another source disagrees". On the gold assertions these rules reproduce the fixture's six relations exactly and answer all nine as-of queries (tested).
This depends on extractors using stable subjects and the predicate vocabulary now listed in the extraction prompt.

### D24. Confidence inputs
`high`: the user said it, or it is stated outright by the user or someone they correspond with. `medium`: stated outright by an unknown sender, or inferred from a known one. `low`: inferred from an unknown sender, or the source is flagged suspicious (injection markers, or a look-alike of the user). No model-reported number is used.

### D25. Corrections are new assertions
Edit creates a `user_stated`, `confirmed` assertion that keeps the original evidence quote, marks the original `corrected`, and links them with `supersedes`. The user's own captured words are stored as `confirmed` on arrival; nothing else ever is. Commitment status can only be tracked after confirmation (API returns 409 otherwise).

### D26. A rule-based extractor is the no-credentials adapter
No model provider credentials exist in this environment, so Slice 1 runs on `HeuristicTriager`/`HeuristicExtractor` behind the same interfaces (AGENT.md: build a local mock adapter and continue). They recognise first-person promises, dated deadlines, "we/I decided", and announced phone numbers — nothing else.
**Their scores are not evidence of product quality.** The rules and the fixture were written by the same author in the same week; commitment F1 0.97 on the fixture will not survive a real inbox. They are the floor the LLM extractor must beat on the golden set, and the offline demo path.

### D27. Anthropic adapter: written, unit-tested, not yet run live
`extraction/anthropic_adapter.py` uses `messages.parse` with a Pydantic output model, a frozen system prefix with the cache breakpoint at its end, and per-call usage/cost accounting. Defaults: triage `claude-haiku-4-5`, extraction `claude-opus-5`, both configurable. Tests use a stand-in client and assert the prefix is byte-identical across sources and users and contains no fixture content.
**Open until a key is available:** real scores, real cost, whether Haiku's larger minimum cacheable prefix means triage calls never cache (likely — the triage prompt is short; options are a longer triage prefix or accepting uncached Haiku calls), and refusal-fallback configuration. The paid eval path requires `--allow-spend`.
**Dependency added:** `anthropic` (official SDK), imported only by the adapter and the factory.

### D28. Typed routes disabled in the app
Expo's typed routes rely on a generated, gitignored file that only the dev server refreshes, which made `tsc` fail on a clean checkout after adding screens. Turned off; a deterministic type check matters more at this size. Revisit when there are enough routes for typos to be a real risk.

### D29. Mock connector stores message bodies
`sources.record` holds the full normalized record, including the body, because the fixture has nowhere to re-fetch from. D9's posture (quotes stored, bodies re-fetched) is implemented with the real Gmail connector in Slice 4; the column is documented as temporary.

## 2026-09-21 — Slice 1 review outcomes and Slice 2

### D30. The pipeline never writes `review` — no exceptions (supersedes part of D25)
D25 let the user's captured notes arrive `confirmed`. The independent review called this a breach of priority 3, correctly: the *note* is the user's, but a due date or party read out of it is an interpretation. Now every capture is stored verbatim as a `memory` assertion created by code, everything interpreted from it is `unreviewed`, and "fact" in the app and the brief means `review = confirmed` (or the verbatim memory itself).

### D31. Assertion identity is where a fact was found, not who found it
Key: (source, kind, hash of the normalized quote, ordinal). Swapping extractor, model, or prompt version meets the user's earlier decisions instead of duplicating them; a rephrased quote for something already dismissed or corrected is skipped; unreviewed guesses a run no longer produces are deleted; anything the user touched is kept. Pipeline relations are rebuilt each run; user-made ones (`made_by = user`) persist.

### D32. Who may update a fact (tightens D23)
Its original sender, the user, or — in the same thread — someone the original message was addressed to, with all of a person's addresses treated as one. Anyone else produces a contradiction at most. A LOW-confidence message produces no relation. **Residual:** sender spoofing; to be closed with Gmail's authentication results in Slice 4.

### D33. "Known sender" means reciprocity (tightens D24)
The user has written to them, or they share a calendar event, as of the message in question. Having emailed the user proves nothing.

### D34. Brief items are chosen by code; writers only word them
`brief/items.py` selects, ranks, de-duplicates, and caps (at most four unreviewed guesses per brief; no low-confidence guesses). A writer receives items and returns wording per item; it cannot add or drop facts, and each item keeps its assertion id. The template writer needs no model; a model writer will sit behind the same protocol. Notifications are a fixed generic string plus a deep link, and an empty brief sends none.

### D35. Demo clock
`PWM_FIXED_NOW` pins time so the September-2026 synthetic mailbox demos sensibly on any date. All time-dependent code goes through `pwm.clock`.

### D36. Eval baseline is committed and gated
`eval/baselines/heuristic.json` + `pwm_eval.check`. A score may only get worse through a visible edit to that file with the reason logged in `docs/PROGRESS.md`. First deliberate change: `signal_emails_dropped_rate` 0.00 → 0.13 when the metric learned to see triage drops.

### D37. Ask Your World retrieves in process, and declines by rule
Retrieval is plain code over one user's live assertions: intent detection (mine / owed to me / deadlines / decision / when / history / lookup), weighted word overlap on subject, value, quote and message context, superseded facts only for questions about the past, low-confidence sources excluded. If the question names something that appears nowhere in the user's world, it declines and says which word. The reasoner receives the retrieved facts and must cite them; no evidence means no answer.
**Why not pgvector/FTS now:** semantic retrieval needs an embedding model, which needs a provider (none configured), and at MVP scale a user's live assertions fit in memory. The `retrieve()` signature is the seam: SQL full-text search and pgvector replace the body when a real mailbox makes this slow or when paraphrase recall (measured on the golden set) demands it.
**Known limit:** word overlap misses paraphrase ("the dental thing" finds nothing about "appointment"). `ask_hit_rate` on the synthetic questions is 0.82 with 0.00 false answers; the misses are facts the stand-in extractor never found.

### D38. Remember / Forget are user actions
`POST /memories` stores the note as a user-capture source, runs the funnel, and then — in `review.remember`, with an audit event — confirms the verbatim memory. Anything read out of the note stays a possibility. `DELETE /memories/{id}` deletes the capture source, which cascades to the memory and everything interpreted from it.

### D39. Model-backed wording is checked by code, item by item
`AnthropicBriefWriter` and `AnthropicReasoner` sit behind the same protocols as the template versions and are selected by `PWM_EXTRACTOR`. Code keeps its own selection and order and then checks the model's work: a brief item falls back to template wording if the model drops it, words an unconfirmed item as fact, or uses a number that is not in the item; extra items are ignored; an answer may cite only the evidence it was given, and an answer that cites nothing becomes a refusal without the model's text being shown. With no evidence, no call is made. Unit-tested against a stand-in client; **never run live**. The Home screen's "what changed" always uses the template writer: it must be instant and free.

### D40. Briefs on a schedule
`pwm.cli tick` runs pending jobs, then makes any daily or weekly brief that is due (none if there is nothing to say; never two within a period). It is meant for cron or a platform scheduler; a long-running scheduler process is unnecessary at this size.

### D41. Connections own their data
Every source records the connector that brought it in. Disconnecting deletes exactly those sources, rebuilds what is left (people only they mentioned disappear; notes the user typed stay), and removes the connection. "Delete everything" deletes the user row and relies on cascade, which a test verifies table by table. Gmail and Calendar payload normalization exists as pure functions (`connectors/google.py`, plain-text part only, `Authentication-Results` header kept for the sender-spoofing work in D32); the OAuth flow, fetching, encrypted token storage, and accounts are deliberately not written blind — they need a Google OAuth client to build against.

## 2026-09-21 — Slices 2–3 review outcomes

### D42. Inferred identity confers no authority (tightens D22 and D32)
An inferred link between two addresses is a *suggestion*: it groups people in the UI and can be split. It does not let the second address update what the first one said, because the evidence for the link (a display name and a self-written signature) is exactly what an impersonator controls. Authority comes only from links the user made by hand. Calendar entries are not the user's own statements either: a connector files every event under the calendar's owner, including invitations from strangers, and an invitation does not make its sender known.
**Cost accepted:** a contact's genuine new address produces "two sources disagree" until the user confirms the link. That is the right failure direction.

### D43. One bad message never stops a mailbox
Anything that can be malformed by a sender (length, characters, structure) is bounded or rejected at construction, and a validation failure is confined to the source that caused it. Only provider failures fail a job, because those are worth retrying.

### D44. Unreviewed rows are always current; reviewed rows are the user's
Each run refreshes unreviewed assertions with the current extraction, rules, and sender trust, recomputes supersession from scratch (a rejected replacement replaces nothing), rebuilds pipeline-made relations, and prunes stored briefs of anything whose assertion is gone. Rows the user confirmed, rejected, or corrected keep their content and their verdict; a rephrased quote from a new model maps onto them instead of creating a twin. Facts sharing a quote are matched by what they say, not by position.

### D45. Migrations are tested against data
`backend/tests/test_migrations.py` loads a database at an earlier revision with the awkward rows (a correction and its original), upgrades to head, downgrades, and upgrades again. Migrating an empty database proves nothing.

## 2026-09-21 — Demo-readiness review outcomes

### D46. Authority is per link, not per person (completes D42)
An address may speak for a person only if it was seen as that person's (`exact`) or the user placed it (`user`), and only once the user has linked that person at all. A guessed address gains nothing from sitting next to confirmed ones. The third review showed the per-person version turned the recommended action — confirm the genuine address — into the attack.

### D47. Hostile input is cleaned at the door and confined to its message (completes D43)
`SourceRecord` strips NUL and bounds text where records are created; `Candidate` rejects NUL; markup scanning is linear by construction (tags cannot span `<`, attributes and whitespace runs are bounded); per-source isolation covers bad values, impossible dates and overflow. Only provider failures fail a job.

### D48. Model wording must stay inside its evidence (completes D39)
For briefs and answers alike, the text a model writes is checked against the *content* it was given — never ids or timestamps: no links, no addresses, no numbers and no capitalised names that are not in that content, no certainty words, and a hedge whenever anything cited is unconfirmed. Reformatted dates and amounts pass. A failure never reaches the user: the same evidence is worded by the template instead. This is deliberately strict, because the fallback is always available and always safe.

### D49. What stands is decided first; relations follow (completes D44)
Each run decides which stored rows are still standing (one draft per row, nothing the user rejected), then recomputes supersession and relations over exactly those. Only rows the run produced are reset, so a confirmed fact whose source yields nothing this time keeps what replaced it. Reworded unreviewed rows are reused rather than re-created, which keeps stored briefs and their links intact.

### D50. Typo tolerance never guesses at names or numbers, and always says so
A one-letter difference in a name or an amount is a different person or a different amount. Fuzzy matching is limited to ordinary lower-case words of seven letters or more with the same first letter, and the answer states what was read as what.

### D51. No authentication means no service outside `local`
Until Slice 4 adds real accounts, every request outside a local environment is refused, regardless of what rows exist.

### D52. History, not appearance, decides who founds a person (completes D46)
Clustering used to promote the address with the longest display name to primary, which handed an impersonator the victim's identity. Now the first address seen founds the person and is the only `exact` one; every address that joins later is a guess until the user says otherwise, and merging two people does not vouch for either's guesses.

### D53. Validity is enforced where records are made (completes D47)
`Party` and `SourceRecord` are the only doors into the system, so they own cleanliness: bounded names and ids, real addresses or none, no NUL or surrogates, aware and plausible times. Code past that point may assume it. Truncating an address is never acceptable, because a truncated address is someone else's.

### D54. A user's dismissal takes effect immediately
Dismissing a replacement frees what it replaced in the same transaction, and the endpoint re-reads the mailbox. Waiting for "the next run" left confirmed facts invisible.

## 2026-09-21 — Slice 4, built against a stand-in for Google

**Founder decisions:** build Slice 4 now against a fake Google rather than wait for an OAuth client; Google sign-in is the only way to sign in.

### D55. What "built against a fake Google" does and does not prove
`pwm.devtools.fake_google` serves the synthetic mailbox through the documented shapes of the OAuth, userinfo, Gmail v1 and Calendar v3 endpoints, as a real separate server in the functional test, and can be made to misbehave (429/5xx with Retry-After, expired access tokens, forgotten history ids, expired sync tokens, a revoked grant, withheld scopes). It proves our side of the contract **as we read the documentation**. It cannot prove Google agrees. Until a real OAuth client exists, Slice 4 is "built, unverified", and the first real sign-in should be expected to find differences.
The synthetic mailbox gives identical pipeline results through the Gmail path and directly (tested), so connector normalization loses nothing the pipeline uses.

### D56. Sign-in flow
System browser → `/auth/google/start` (PKCE S256, random `state` stored server-side with the verifier, allow-listed app redirect) → Google → `/auth/google/callback` (state is single-use and expires in 10 minutes; scopes are checked, so declining mail access is not a sign-in; email must be verified) → redirect to the app with a **single-use login code** valid two minutes → the app POSTs it for a session token. The session token never appears in a URL; only its hash is stored; Google's tokens never leave the server. Google's account id identifies the user. A verified email adopts an account never linked to Google (the local development identity) and never one linked to a different Google identity.
Userinfo is read with the access token we just received over TLS from Google's token endpoint, so no ID-token signature checking is needed and no JWT library is added.

### D57. Tokens and bodies are encrypted with a key that is not in the database
AES-256-GCM, random nonce per value, the purpose bound in as associated data (a token cannot be replayed as a body), `enc:v1:` prefix for key rotation later. `PWM_DATA_KEY` is required before Google can be used at all. Message **bodies are encrypted at rest**; metadata (sender, subject, dates, labels) stays in the clear so it can be queried.
**This revises D9/D29:** bodies are stored (encrypted), not re-fetched on demand. The pipeline re-reads every source on every run (D19, D44) — that is what lets new rules, new prompt versions and the user's corrections take effect — and that needs the text. A retention window after which bodies are purged and their already-verified facts frozen is the intended next step; it is recorded here as **not built**.

### D58. Sync: newest first, one page per job, opaque cursors
Connectors return `FetchResult(records, cursor, more, skipped)`; the cursor is opaque to everything else. Gmail: capture the history id **before** the backfill so nothing arriving during it is missed; list `newer_than:90d` newest first, 50 per page, one page per job (processed and visible before the next is fetched); then incremental by `history.list`; a forgotten history id (404) restarts the backfill, which idempotent ingestion makes harmless. Calendar: window read, then `syncToken`; 410 re-reads the window. An edited event is a **new immutable source** (its id carries `updated`), so a moved meeting is reported as a change by ordinary reconciliation.
429/5xx retry with backoff honouring Retry-After, bounded at five attempts; a 401 refreshes the access token once; a revoked or expired grant marks the connection `needs_reconnect` and the job is *done*, not retried forever. Errors carry a status code, never a response body.
**Not handled yet:** messages deleted in Gmail are not removed here; label changes are not tracked.

### D59. Forged senders
Gmail's `Authentication-Results` header is kept. A message that fails DMARC, or both SPF and DKIM, is flagged suspicious: low confidence, no ability to update or dispute anything, a warning on its inspection screen. Absent results are not held against a message. This closes the residual noted in D32/D42 for mail that Gmail itself judged forged.

### D60. Taking it back
Disconnecting a Google source deletes what it brought in; when the last one goes, the grant is revoked at Google and the stored token destroyed whether or not Google could be reached. "Delete everything" revokes first, then deletes the user and everything by cascade; a signed-in account is simply gone.

### D61. Dependencies added
`httpx` (HTTP client; already present for tests) and `cryptography` (AES-GCM). In the app: `expo-web-browser` (system-browser auth sessions) and `expo-secure-store` (Keychain/Keystore), both part of the Expo SDK. The fake Google parses form bodies by hand so that test tooling adds no dependency.

## 2026-09-21 — Slice 4 review outcomes

### D62. The login code is bound to the app that started the sign-in (extends D56)
PKCE protects the leg between us and Google. The leg between us and the app needed the same idea: the app generates a secret, sends its SHA-256 to `/auth/google/start`, and must present the secret to `/auth/session`. That one mechanism closes two holes the review found: another app intercepting the code of a sign-in *the real app started*, and login CSRF (a link that signs the victim into the attacker's account). An app holding no secret refuses to redeem anything. Redirects are matched exactly (scheme, host, path), never by prefix; Expo Go's address is accepted only in `local`. A sign-in attempt is spent, and the spend committed, before Google is called.

### D63. Connections are created by users, never by jobs
A queued job is a promise made in the past. It may act on a connection that still exists; it may never bring one back. Disconnecting deletes that connection's pending jobs, there is at most one pending sync per connection, and a job is `running` while it runs so its own follow-up page is not mistaken for a duplicate.

### D64. Syncs recur, fail visibly, and recover from stale cursors
`cli tick` queues a sync for every healthy connection older than `PWM_SYNC_MINUTES` — without it nothing would ever be read after the first backfill. A sync that fails for good sets the connection to `error` with the exception class. Stale Gmail page tokens and Calendar sync tokens restart the read rather than wedge the cursor. 403 is retried, because Google reports rate limits that way.

### D65. What a calendar version may say
An edited event is a new immutable source (D58), but only a version that says something new speaks: a cancelled latest version silences the event, and an older version is silent when its successor has the same time. So a moved meeting is a change, while an RSVP or a description edit is nothing.

### D66. Keys have ids, reads do not need them, and revocation is reported honestly (revises D57)
`enc:v2:<key id>:…`; old keys listed in `PWM_DATA_KEYS_OLD` still read; `cli reseal` brings plaintext-era bodies and old-key values under the current key. Listing and inspecting what is known uses clear metadata and degrades to "quote without surroundings" when bodies cannot be read; anything that would reprocess returns 503 and changes nothing. If our copy of a grant is unreadable we cannot ask Google to revoke it, so "delete everything" says `google_access_revoked: false` instead of implying otherwise.
Stated plainly, because an earlier comment overstated it: evidence quotes and extracted values are stored in the clear. Encrypting bodies keeps the bulk of someone's mail out of a database dump; it does not make a dump harmless.

### D67. The server fails closed
`PWM_ENVIRONMENT` defaults to `production`. Only an explicit `local`, on a loopback public URL, serves the development user without a session, offers the demo mailbox, or accepts Expo Go redirects. A forgotten variable must cost convenience, never safety.

### D68. One writer per user
Syncing, disconnecting and rebuilding a user's world each take the same per-user advisory lock before looking at anything. Without it, a disconnect could not see a page a worker was still writing and left it behind. (D63's "a job is running while it runs" was true only inside the job's own transaction; the lock is what actually serialises.)

### D69. What binding the login code does not do (corrects D62)
It does not stop a malicious app that registers the `pwm://` scheme from *starting its own* sign-in: the user sees the genuine consent screen, and the code comes back bound to the attacker's secret. This is the app-impersonation problem of custom URL schemes (RFC 8252 §8.6). The remedy is claimed HTTPS redirects — universal links on iOS, app links on Android — which need a real domain and the store identities of Slice 5. Until then it is a documented residual for the native app. The web app has none: a code started elsewhere lands in a tab that holds no secret and is refused.

### D70. A calendar event is one event across its versions
Versions are separate immutable sources (D58, D65), but the user's review belongs to the event: a confirmed event carries its confirmation through an edit that does not move it, and an event that is called off is marked `cancelled` — kept, with the user's review intact, and absent from every live view.

## 2026-09-21 — Slice 5, the parts a laptop can build

### D71. Push is announced, never described
`ExpoPushNotifier` writes the in-app inbox row first and then asks Expo to deliver the same fixed title and a deep link to every registered device. Tokens Expo reports dead *in the ticket* are dropped; most delivery failures arrive later in receipts, which are not fetched yet, so a dead device is dropped one push late. Expo being unreachable loses nothing but the buzz. A phone belongs to whoever is signed in on it; five devices per user. Devices register with a validated Expo token and unregister on sign-out. Selected by `PWM_PUSH_URL`; empty means inbox only, which is what tests and the demo use.
**Not verified:** no push has reached a phone. `getExpoPushTokenAsync` needs an EAS project id, which needs the founder's Expo account; the app declines quietly without one.

### D72. Deep links and app links
`pwm://brief/<id>` opens the brief and counts the tap; `GET /briefs/{id}` is owner-checked. The identities that let a phone trust `https://<api host>/auth` as ours — the remedy for the custom-scheme residual in D69 — are served at `/.well-known/…` from configuration and are absent until the store identities exist. `app.json` and `eas.json` carry the placeholders and say what to fill in.

### D73. Optional app lock
Biometrics or passcode on foreground, off by default, stored on the device, not offered on the web. Untested on a device.

### D74. A first read rebuilds the world on the first page, every tenth, and the last
Rebuilding is a whole-mailbox pass (D19, D44). Doing it per page made a 90-day read quadratic; doing it three or four times keeps "something within minutes" without that. What triggers a rebuild is whether anything is *waiting* since the last one, never whether the current page added it — the first version of this rule left mail unprocessed when a final page added nothing, and the review caught it. Incremental syncs rebuild once each.
