# Progress

The running record of the build. Updated at every step; never rewritten after the fact.

**How to read it:** the status table says where things stand now; the log below says how they got there. `docs/decisions.md` holds the *why* behind design choices; this file holds *what happened*.

**Discipline for every major step** (a slice, or a comparable unit of work):
1. Implement, with tests.
2. `scripts/verify.sh` — regression (format, lint, types, all test suites, migration check, eval regression gate) and functional (real server + real database + user journeys, production web build).
3. Independent code review of the step's diff, by a reviewer that did not write it. Findings are listed here with their disposition: fixed, deferred (with reason), or rejected (with reason).
4. Re-run `scripts/verify.sh` after fixes. Log the result. Commit.

Working constraint (founder, 2026-09-21): reach a showable, demo-ready MVP **without** the founder's model API key and **without** real Gmail/Calendar access. Pause only where one of those is strictly required, and say why.

## Status

| Step | State | Verified by |
|---|---|---|
| Design review and plan rewrite | done | commit `d2ac143` |
| Phase 0 — scaffolding, fixture, adversarial set, eval harness, threat model | done | commit `0411ba5` |
| Slice 1 — Commitment Radar | done; independently reviewed, 15 findings fixed | commits `02c1c86` + review-fix commit; verify green |
| Progress tracking + verify gate + functional journeys + eval regression gate | done | this file; `scripts/verify.sh` |
| Slice 2 — What changed + World Brief | done; independently reviewed, findings fixed | commits `00a624e` + review-fix commit; verify green |
| Slice 3 — Ask Your World + Remember / Correct / Forget | done; independently reviewed, findings fixed | same |
| Demo readiness — onboarding, connections/disconnect/delete, same-person confirmation, demo launcher and script, in-browser checks | done; independently reviewed, findings fixed | commit `926d450` + next; verify green (122 tests, 87 functional checks incl. the built app in headless Chrome) |
| Slice 4 — accounts, real Gmail/Calendar | **built against a stand-in for Google; unverified against Google itself** (founder chose this on 2026-09-21); independently reviewed, findings fixed | branch `slice-4`; verify green |
| Slice 5 — phone builds, real push | not started; store/TestFlight builds **need founder** (Expo / Apple / Google accounts) | |
| Live LLM evaluation | blocked: **needs founder** (API key + spend approval) | |

## Waiting on the founder
None of these blocks the demo. Each one is a hard stop for the step named, and nothing can stand in for it.

| What | Why only you | What it unblocks |
|---|---|---|
| **Model API key + approval to spend** (`uv run python -m pwm_eval.run --system anthropic --allow-spend`) | It is your account and your money; the run sends the synthetic mailbox's text to the provider. Rough size: about 75 extraction calls plus triage calls — an estimate, not a measurement. | The first real quality numbers; whether Haiku triage ever caches; tuning the prompt. Until then **every score comes from rules I wrote against mail I wrote**. |
| **Label ~200 threads of your own mail** (`uv run python -m pwm_eval.golden <takeout.mbox>`; stays on this machine, gitignored) | Only you can judge what in your inbox is a real commitment or decision. | The only honest benchmark. Also the evidence for the Decision Memory gate. |
| **Google Cloud project + OAuth client, and start restricted-scope verification** (decisions D15) | Needs your Google account and identity; verification and the annual security assessment take weeks to months. | All of Slice 4: real Gmail/Calendar, accounts, encrypted tokens, sender authentication (D32/D42 residual). Writing that code blind was deliberately avoided. |
| **Expo account; Apple and Google developer accounts** | Store and TestFlight builds are tied to them. | Slice 5: installed phone apps and real push. |
| **Try it on a phone with Expo Go** (`docs/local-dev.md`) | This machine has no Android SDK or emulator. | Closes the one open Slice 1 acceptance item ("runs in an emulator from the same code"). |
| **Open the gates or not**: passive Decision Memory, Customer Advocate drafts | Product scope is yours (CLAUDE.md). | Slices 7–8. Evidence so far: decisions are rare even in the synthetic mail (5 in 122), and consumer issues already surface as brief items. |

## How to resume
1. Read this file's status table, then the last log entry.
2. `scripts/verify.sh` must be green before and after any change.
3. `scripts/demo.sh --loaded` and `docs/demo-script.md` show what exists.
4. Follow the discipline at the top for every major step, and record findings here.

## Log

### 2026-09-21

**Design review.** Challenged the original plan; rewrote CLAUDE.md, AGENT.md, TECHNICAL_BRIEF.md, README.md, both prompts; added `docs/decisions.md` (D1–D14). Stack chosen: Expo app + FastAPI/Postgres. Commit `d2ac143`.

**Phase 0.** Backend skeleton, Expo app, deterministic fixture (122 sources: 68 noise, 10 adversarial, 15 calendar; 37 gold assertions at the time), eval harness with oracle and gullible systems testing the metrics, local golden-set labeller, docs (architecture, threat model, env, local dev), Google restricted-scope facts verified (D15). Baseline recorded: recall 0.00 everywhere by design. 20 backend tests, 2 app tests. Commit `0411ba5`.

**Slice 1 — Commitment Radar.** Pure funnel (prefilter → visible text → triage → extraction → quote verification → people resolution → reconciliation → confidence); Postgres schema + migration; idempotent ingestion, stage-result cache, retrying worker, cascade deletion; review actions as the only writer of `review`; API; app screens (Needs attention, Where this came from, Edit); rule-based stand-in stages; Anthropic adapter written and unit-tested against a stand-in client (never run live). Fixture extended: every calendar event is now a gold fact (51 gold assertions). 64 backend tests, 7 app tests. Decisions D19–D29. Commit `02c1c86`.
- Acceptance (AGENT.md Slice 1): two addresses → one person with both sources ✔ (test); changed phone / moved date keep history and as-of returns the old value ✔ on gold assertions (test) — but only 0.33 through the rule-based extractor, which does not extract those facts; every stored assertion has a verified quote ✔; injection suite clean ✔; precision **and** recall reported ✔ (rule-based only; golden set not available); runs in browser ✔ — **emulator not tested**.
- Eval (rule-based, synthetic — not product quality): commitments P 0.94 / R 1.00; decisions 1.00 / 0.80; facts 1.00 / 0.52; people 1.00 / 1.00; relations 0 / 6; temporal 0.33; noise reaching model 0.29; injection clean.

**Tracking and gates.** Added this file; `scripts/verify.sh`; `scripts/functional_test.py` + `scripts/journeys.py` (fresh database → migrations → CLI demo → real uvicorn → user journeys over HTTP; 28 checks); `pwm_eval.check` with a committed baseline (`eval/baselines/heuristic.json`, 21 scores) so an eval drop fails the gate; `pwm.cli reprocess`. First full run: **ALL GREEN** (68 backend/eval tests, 7 app tests, 28 functional checks, web build ok).

**Slice 1 independent review.** A separate reviewer examined `0411ba5..02c1c86` plus the new scripts, reproducing findings with throwaway probes against the test database. 15 ranked findings + 9 smaller ones. All were real. Dispositions:

| # | Finding | Disposition |
|---|---|---|
| 1 | Changing extractor/model/prompt version duplicated every assertion and resurrected dismissed ones | **Fixed.** Identity is now (source, kind, quote hash, ordinal), independent of who extracted it. A rephrased quote for something the user dismissed/corrected is skipped. Unreviewed machine guesses a run no longer produces are retired. Tests added. |
| 2 | A suspicious / low-confidence message in the same thread (or a spoofed sender) could supersede and hide a trusted or confirmed fact | **Fixed.** Only the original sender, the user, or an addressee of the original (same thread) may update; outsiders produce a contradiction; LOW-confidence messages produce no relation at all. Tests added. Residual: a spoofed From passes until real mail gives us SPF/DKIM results (Slice 4). |
| 3 | Unique index over unbounded quote text: one long quote failed the whole user's job | **Fixed.** Hash in the key; `Candidate` fields are length-bounded, so oversize output is dropped at the boundary. |
| 4 | Pipeline wrote `review="confirmed"` for user captures — a breach of priority 3 | **Fixed, and the rule is now absolute:** the pipeline writes `unreviewed` only. Each capture is kept verbatim as a `memory` assertion (made by code); anything *interpreted* from a note is a possibility until confirmed. App `isFact` = confirmed only. |
| 5 | Any stranger who emailed once counted as a "known sender" → HIGH confidence | **Fixed.** Known = the user has written to them or shares a calendar event, as of that message. |
| 6 | Triage cache shared across providers; extraction cache ignored the model | **Fixed.** Cache keys include implementation and model. |
| 7 | Hidden-markup stripping bypassed by nesting, unquoted attributes, tiny/white text | **Fixed.** Nesting-aware removal; more hiding styles; `hidden` attribute; unclosed hidden element hides the rest. Text outside hidden elements is untouched. 6 tests. |
| 8 | People survived deletion of the only source that mentioned them | **Fixed.** People are re-derived each run and pruned; `delete_sources()`; user-placed identifiers kept. |
| 9 | A failed job rolled back cached model results and spend audit rows → retries re-paid | **Fixed.** Cache rows are replayed after the rollback. |
| 10 | `job.last_error` could contain message content | **Fixed.** Exception class name only. Per-user advisory lock added so two workers cannot collide. |
| 11 | `signal_emails_dropped_rate` could not see triage drops | **Fixed.** It now reads 0.13 for the rule-based triager (was a blind 0.00). Baseline updated deliberately for this reason. |
| 12 | Quote matching gameable by quoting whole messages; spurious relations collapsed into one false positive; verification rate was 1.0 by construction | **Fixed.** Bounded quote length in matching; injection check measures coverage of the injected span; each unmatched relation counts; verification rate includes what the gate dropped and checks against visible text. |
| 13 | `has_conflict` never cleared after dismissing the other side | **Fixed.** |
| 14 | Oversize / NUL / empty corrections caused 500s or stored blanks | **Fixed.** Validated; DB errors become 422. |
| 15 | Job idempotency key could swallow a new batch | **Fixed.** One pending job per user; keys are unique. |
| — | Same quote supporting two facts collapsed to one | **Fixed** (ordinal). |
| — | Refusals / parse failures cached forever | **Fixed** (`cacheable=False`; spend still audited). |
| — | Untrusted text could close the `<source>` tag | **Fixed** (delimiter tags sealed). |
| — | Evidence highlight failed when quote marks/whitespace differed | **Fixed** (API returns before / quote / after). |
| — | Look-alike sender labelled "You → …" | **Fixed** (direction by address). |
| — | "next Friday" = "Friday"; "may 5" read as a date | **Fixed.** |
| — | Extraction prefix (~2.5k tokens) below some models' cache minimum | **Deferred.** Fine for the default extraction model; triage on Haiku likely never caches. Needs a live key to measure (D27). |

Reviewer confirmed sound: ownership checks, the `user_stated` gate, ingestion idempotency, source→assertion/relation/event/cache cascades, `pipefail` in the verify script.

**Slice 2 backend.** Demo clock (`PWM_FIXED_NOW`); code-side selection, ranking, de-duplication and per-kind caps of brief items; template writer (no model) that words unconfirmed items as possibilities; briefs, generic-payload notifications (in-app inbox stand-in for push), product events; `/home`, `/visits`, `/briefs`, `/notifications`, `/events`; `pwm.cli brief`. Rule-based extractor extended to priced/dated facts (price changes, premiums, quotes, return windows, appointments) — still a stand-in. Sentence splitting no longer breaks on "Dr.". Same-thread facts with the same predicate are treated as the same matter.
- Eval (rule-based, synthetic): commitments 0.94 / 1.00; decisions 1.00 / 0.80; facts 1.00 / 0.84 (was 0.52); relations 0.67 / 0.33 (was 0 / 0); temporal 0.44; signal dropped 0.13; injection clean.
- `scripts/verify.sh`: **ALL GREEN** — 99 backend/eval tests, 7 app tests, 46 functional checks, migration round-trip, web build.

**Slices 2 and 3 — app and Ask.** App: Your World home (what changed with before/after evidence, needs-attention preview, remembered), full needs-attention list, World Brief with "was this useful?", Ask with cited evidence and suggestions, Remember modal, Forget on notes; headings now depend on the kind of fact (a price change is a "possible detail", not a "possible commitment"). Ask: code-only retrieval with intent detection; declines when there is no evidence or when the question names something never seen; low-confidence sources cannot answer. Remember/Forget are user actions with audit events. Brief wording formats dates and money. Eval gained 15 gold questions: `ask_hit_rate` 0.82, `ask_false_answer_rate` 0.00 (the planted-by-attacker question gets no answer); baseline updated to include them. Found by looking at the screens, not by tests: ISO timestamps and bare numbers in headlines; a curly apostrophe ("Dana’s") turned "s" into a search term and caused a refusal — both fixed with tests. Commit `00a624e`.

**Demo readiness.** Connector protocol; demo-mailbox connector (newest first, resumable cursor); Gmail/Calendar payload normalization as pure tested functions; `connections` table and `sources.connector`; sync / disconnect / delete-everything; onboarding screen ("Connect your life") and a "Connections and your data" screen; `scripts/demo.sh` (starts at onboarding; `--loaded`, `--keep`); `docs/demo-script.md`. The functional test now also builds the production web app against the test server and checks in headless Chrome that a new user sees onboarding and that, after connecting, Your World shows a real hedged change with a readable amount. Two process bugs found and fixed along the way: `trap 'kill 0'` in the launcher killed its parent's process group; Metro's cache kept a stale `EXPO_PUBLIC_API_URL` baked into the bundle (`--clear`). Commit `926d450`.
- `scripts/verify.sh`: **ALL GREEN** — 122 backend/eval tests, 8 app tests, 87 functional checks.

**Slices 2–3 independent review.** A second separate reviewer examined `02c1c86..00a624e` against a frozen snapshot, reproducing 14 of 15 findings with probes. All were real. Dispositions:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high | An impersonator with a compatible display name and the right surname in their message inherited the real sender's identity (inferred link) and could **supersede** their facts | **Fixed.** Inferred links confer no authority. Only links the user made by hand let a second address update a fact; otherwise it is a contradiction. Regression test with the reviewer's scenario. Cost: Priya's genuine second address now disputes rather than replaces until the user confirms the link. |
| 2 | high | The new length bounds raised inside the funnel for rule-based, calendar and note candidates: one long sentence or subject failed **every** run for that user | **Fixed.** Code-made candidates are bounded at construction; run-on sentences are skipped; a validation failure is isolated to its source (`outcome.failed`) and never stops the mailbox. Provider errors still propagate so jobs retry. Test. |
| 3 | high | Migration 0003 failed on any database holding a correction (key collision), mislabelled user relations as pipeline-made, and could not be downgraded | **Fixed.** Ordinals are numbered per (source, kind, quote); correction relations become `made_by = user`; constraint drops are `IF EXISTS`; the old key is deliberately not restored on downgrade. **New test migrates a populated database** up, down and up again — the first version of the fix failed that test, which is why it exists. |
| 4 | med | Forgetting a note or deleting a source left its text inside stored briefs | **Fixed.** Briefs are pruned on every run; an emptied brief is deleted. Test uses the reviewer's scenario. |
| 5 | med | `remember` returned 500 for notes starting with ">" or containing markup, and a raw validation dump for long notes | **Fixed.** A user's note is visible text from first character to last; long notes are evidenced by their opening; errors are generic. Test. |
| 6 | med | Dismissing a wrong "update" left the original superseded: no live fact at all | **Fixed.** Supersession is recomputed each run; a rejected replacement replaces nothing; pointers to user corrections are untouched. Test. |
| 7 | med | Matched rows were never refreshed, so rule fixes and changed trust never reached existing rows | **Fixed.** Unreviewed rows always take the current extraction; confidence is refreshed for all. Test. |
| 8 | med | A confirmed row got an unreviewed twin when a new model rephrased the quote | **Fixed.** The rephrase guard covers confirmed rows too and keeps them in the run. Test. |
| 9 | med | Positional ordinals let a surviving fact be swallowed by a dismissed sibling | **Fixed.** Siblings sharing a quote are matched by what they say. Test. |
| 10 | med | Ask refused ordinary questions ("show me my deadlines", "what am I owed", typos) and named a stemmed fragment | **Fixed.** Wider stop/intent vocabulary, fuzzy matching for typos, refusal quotes the user's own word. 8 parametrized tests from the reviewer's table. |
| 11 | med | A superseded confirmed commitment was shown first and unhedged; "before Friday" triggered history mode | **Fixed.** Replaced facts read "Earlier: … — later replaced"; history needs explicit past wording. Tests. |
| 12 | med | An unsolicited calendar invite made its sender "known" → high confidence | **Fixed.** Only mail the user sent establishes a relationship. Calendar entries are also no longer treated as the user's own statements. Test. |
| 13 | low-med | "What changed" judged by when mail was sent, not when it was learned; a 61-minute pause reset it | **Fixed.** Uses learned-at with a 30-day floor; same-visit window is 6 hours. |
| 14 | low | `inf` / `nan` amounts crashed brief rendering | **Fixed.** Test. |
| 15 | low | Conflicts hidden behind due-soon; stacked notifications; unhandled rejection in the Brief screen; missing baseline passed the gate; cache snapshot before the lock | **All fixed.** Tests for the first, second and fourth. |

Reviewer confirmed sound: forget/ownership checks, double-remember, correction chains, stale-row retirement, the pipeline never writing `review`, memory and `user_stated` gates, low-confidence exclusion from Ask and briefs, hedged wording, generic notification title, no content in worker errors, input validation on new endpoints, fixed clock everywhere time matters, first/second/third visit logic, verify and demo scripts.

- `scripts/verify.sh`: **ALL GREEN** — 155 backend/eval tests (incl. populated-database migration test), 8 app tests, 87 functional checks; eval gate no regression across 24 scores.

**Also built while the review ran:** scheduled briefs (`pwm.cli tick`, D40); model-backed brief writer and reasoner with code-side guards, never run live (D39).

**Same-person confirmation.** The identity fix (D42) said only links "the user made by hand" carry authority, but nothing let the user make one. Added `GET /people`, confirm and split endpoints (each re-reads the mailbox afterwards), and an "Is this the same person?" card in *Connections and your data* that explains why it asks. Test shows the effect end to end: before confirming, Priya's second address can only dispute the Saturday plan; after, her "change of plan" supersedes it. Reprocessing never undoes a confirmed link (functional journey).
- `scripts/verify.sh`: **ALL GREEN** — 158 backend/eval tests, 8 app tests, 95 functional checks.
- Checked: no Android SDK on this machine, so the emulator acceptance item stays open; Expo Go on a phone is the quickest route.

**Demo-readiness independent review.** A third separate reviewer examined `00a624e..42d8ea7` from a frozen snapshot, with its own throwaway database, and was asked specifically whether the earlier fixes hold. 15 ranked findings plus smaller ones; three earlier fixes were incomplete. Dispositions:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high | Identity authority was granted per *person*: once the user confirmed Priya's genuine second address, an impersonator's **guessed** address on the same person could also supersede her facts | **Fixed.** Authority is per link: only `exact` and `user` identifiers, and only for people the user has linked. Test with the reviewer's scenario. |
| 2 | high | Only `ValidationError` was isolated per source; a NUL byte in a mail body made the insert fail and wedged every later run for that user | **Fixed.** Records are sanitised where they are made (NUL removed, bodies bounded at 200k characters); candidates reject NUL; isolation covers bad values, impossible dates and overflow. Provider errors still propagate. Tests. |
| 3 | med | Model-written brief guards checked only the headline, by prefix, and allowed any digit that appeared in ids or timestamps | **Fixed.** Every field the model writes is checked against the item's *content* (never ids/timestamps): no links or addresses, no numbers or capitalised names absent from the content, no certainty words; reformatted dates and amounts are allowed. Anything else falls back to the template. Tests include the reviewer's examples. |
| 4 | med | Model answers were never checked against their evidence | **Fixed.** Same grounding check against the cited facts plus the question; a guess stated without a hedge is rejected; on failure the *same evidence* is worded by the template. |
| 5 | med | `<items>`, `<facts>`, `<question>` were not sealed | **Fixed** (and `<system>`). Test. |
| 6 | med | After dismissing a wrong update, a later genuine update no longer superseded the original (two live prices, no conflict shown) | **Fixed.** Supersession and relations are recomputed over exactly the facts still standing — one per stored row, nothing rejected — so the chain re-forms around the dismissed link. Test. |
| 7 | med | Supersession was reset on confirmed rows a run did not produce, resurrecting a replaced fact as live | **Fixed.** Only rows the run produced are reset. Test. |
| 8 | med | Typo tolerance answered about the wrong person or amount (Christina→Christine, 1450→14500) | **Fixed.** Guessing applies only to ordinary lower-case words of 7+ letters with the same first letter; never to names or numbers; and the answer says "I read X as Y". Tests. |
| 9 | med | After disconnecting the last source the app showed only onboarding, leaving kept notes — and "Delete everything" — unreachable | **Fixed.** Onboarding is for an empty world; otherwise Home shows with a "nothing is connected" link to data controls. |
| 10 | med-low | A rephrased quote churned row ids, deleting stored briefs and leaving dangling notifications | **Fixed.** Unreviewed rows are reused when the same fact is reworded; a removed brief takes its notification with it. Tests. |
| 11 | med-low | Two near-identical candidates could make a confirmed fact supersede itself | **Fixed** (one draft per row; self-reference guarded). Test. |
| 12 | med-low | The one-to-one pairing shortcut attached a *different* fact from the same sentence to a dismissed row, losing it | **Fixed.** The shortcut requires the same predicate unless the row is unreviewed. Test. |
| 13 | med-low | Markup stripping was quadratic on unclosed tags (160 KB ≈ 23 s) | **Fixed.** Tags cannot span `<`, attributes and whitespace runs are bounded, bodies are capped. Timing tests (<2 s for 120 KB of hostile input). |
| 14 | low-med | `verify` could go green with no Chrome and therefore no web build; fixed static port | **Fixed.** The build always runs; missing Chrome prints a WARNING (or fails with `PWM_REQUIRE_BROWSER=1`); ports are chosen free; a dead static server fails the check. |
| 15 | low-med | Outside `local`, requests were served unauthenticated once the dev user row existed — including `DELETE /me` | **Fixed.** There is no authentication yet, so outside `local` every request is refused. Test. |
| — | low | Google payload edge cases (bad base64, missing header values, duplicate From, null parts, attachments as body, naive datetimes that would break sorting for the whole user) | **Fixed.** `MalformedPayload`, first-From-wins, attachments skipped, naive times made UTC, `normalize_all` skips and counts bad records. Tests. |
| — | low | "99:99 pm" stored as a time; spoofed From-the-user made its recipient "known"; cursor `>` could miss a record; one user's brief failure aborted the tick; tick ignored the configured writer; brief tie on a pinned clock; app double-tap, stale error and stuck-button states | **All fixed.** Tests for the first three. |
| — | low | Migration 0004 labels pre-existing sources `manual`, with no connection to disconnect | **Accepted** for pre-release data (there is none outside development); "Delete everything" removes them. Noted here so it is not forgotten before real users exist. |

Reviewer confirmed sound: every cascade on `DELETE /me` table by table, disconnect scope and copy, correction chains, memories across runs, confirmed rows never changing content, split fully revoking authority, inferred links alone conferring nothing, the length bounds, nested hidden elements, brief pruning null-handling, scheduled-brief arithmetic, learned-at logic, migration 0003 with data, demo gating, `pipefail`, remember/forget, cache replay, and the no-evidence-no-call paths.

- `scripts/verify.sh`: **ALL GREEN** — 193 backend/eval tests, 8 app tests, 96 functional checks; eval gate no regression across 24 scores.

**Clean-checkout check.** Cloned the repository into a scratch directory, installed from the lockfiles only (`uv sync`, `npm ci`), and ran `scripts/verify.sh --quick`: **ALL GREEN** (161 tests, eval gate, app checks). One thing learned: `docker compose` in a differently named directory starts a second, unused database container; removed it. Also: selecting the model path without credentials now fails with a clear message, and provider failures reach the app as a generic 503 rather than a 500 (the provider's own error text can quote the request, so it is never passed on).

**Verification review of the last fix batch.** Because the third review found earlier fixes incomplete, a fourth reviewer was asked only to break the fixes in `2522f4e`. 9 substantiated problems (2 high). Dispositions:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high | Per-link authority was bypassable: clustering made the address with the *longest display name* the primary, so an impersonator ("Priya K Raman") was stored as `exact` on the real Priya's person and inherited authority once the user confirmed any link | **Fixed at the root.** The first address *seen* founds a person; every address that joins a cluster or an existing person is `inferred`, whatever its name. Exactly one `exact` per person (tested as an invariant). Merging people no longer vouches for their guessed addresses. |
| 2 | high | A 250-character sender name, an over-long address, or a lone surrogate passed ingestion and then failed the people insert on every run | **Fixed at the door.** `Party` and `SourceRecord` clean and bound everything where records are made: names truncated, addresses validated (too long or no `@` is invalid, never truncated), ids bounded, surrogates and NUL removed, naive times made UTC, implausible years rejected. Tests. |
| 3 | med | Dismissing a wrong update over the API left the original hidden until some later run | **Fixed.** Dismissal frees what it replaced immediately, and the endpoint re-reads the mailbox so a later genuine update takes its place. API test. |
| 4 | med | A dismissed fact came back when a new extractor reworded both predicate and value ("price $1450" → "rent 1450 USD monthly") | **Fixed.** Values are compared by their figures when they have any, by words otherwise. Test covers both this and the opposite case from the third review (a genuinely different fact in the same sentence). |
| 5 | med | The grounding check for model wording accepted sentence-initial names, number words, recombined amounts, magnitudes, AM/PM flips, scheme-less links, more certainty words, negation, and instructions | **Tightened** for everything cheap to get right (11 rejection tests, 3 acceptance tests). **Known and documented limits:** a lower-case name, or true words recombined into a false sentence, still pass. This layer sits behind code-side selection and in front of a source link on every item; the model path remains never run live. |
| 6 | med-low | Typo tolerance still corrected into a name unless the name was Title-case and not first | **Fixed.** A question word can never be corrected *into* a word that is a person's name in the user's world, however it is capitalised; ordinary capitalised words are corrected again. Tests. |
| 7 | med-low | The length bounds added for linear time let a long attribute smuggle a hidden element past detection | **Fixed.** No length bounds: `[^<>]` alone gives linear time. Whitespace in attributes is collapsed before matching, so padding cannot evade it either. Tests, including the timing tests. |
| 8 | low-med | A confirmed fact could stay superseded by a rejected row | **Fixed** by #3. |
| 8b | low-med | After a user correction, a later update from the same sender neither supersedes nor disputes it | **Open — deliberate for now.** The user's statement outranks mail, but a later change should at least be shown as a dispute. Needs a product decision on wording; recorded so it is not lost. |
| 9 | low | Wrongly shaped Google payloads (`AttributeError`, deep nesting) escaped `MalformedPayload`; missing ids; senders without a domain | **Fixed.** Tests. |
| — | low | A model response that fails schema validation is isolated per source but its spend is not recorded | **Open.** Only reachable on the model path, which has never run; to fix when it does. |

Could not break: NUL and body handling, the confirm → supersede → dismiss → update chain, no self-supersession, no identity-key violations under swapped or overlapping quotes, row reuse keeping ids, delimiter sealing, linear-time stripping, the functional test's build and port handling, the auth gate.

- `scripts/verify.sh`: **ALL GREEN** — 227 backend/eval tests, 8 app tests, 96 functional checks; eval gate no regression across 24 scores.
- Live demo re-walked on current code: onboarding → connect (122 sources, 49 understood) → Ask answers with evidence → Home shows changes and the dispute card.

**Where the reviews leave things.** Four independent reviews produced 54 ranked findings; 52 are fixed with regression tests and 2 are open by decision (above). Each review found something the previous fixes had missed, mostly in identity authority and in what survives reprocessing. The honest reading is that these two areas are where a fifth review should start once real mail and a real model are in play.

**Merged.** `phase-0` fast-forwarded into `master` at `ca3e753` at the founder's request.

**Slice 4 — accounts, Gmail, Calendar (against a fake Google).** Founder decisions: build now against a stand-in rather than wait for an OAuth client; Google sign-in only. Branch `slice-4`.
- Built: `PWM_DATA_KEY` AES-256-GCM encryption for refresh tokens and message bodies; Google sign-in through the system browser with PKCE, single-use state, allow-listed redirects and a single-use login code (no token in any URL); sessions (hash only stored), sign-out; bearer-aware identity with the dev user confined to `local`; Gmail connector (history id captured first, newest-first 90-day backfill in pages of 50, one page per job, incremental by history, restart on 404); Calendar connector (sync tokens, 410 fallback, edited events as new immutable sources so a moved meeting is a "change"); bounded retries honouring Retry-After; access-token refresh mid-sync; `needs_reconnect` for a revoked or expired grant; revoke-and-destroy on disconnect and on delete-everything; forged-sender flagging from `Authentication-Results`; app: "Continue with Google", `/auth` return route, secure token storage, sign-out, reconnect, sync status. Decisions D55–D61.
- `pwm.devtools.fake_google`: OAuth, userinfo, Gmail v1 and Calendar v3 in their documented shapes, serving the synthetic mailbox, with failure injection. Runs in-process for unit tests and as a **separate server** in the functional test. `FAKE_GOOGLE=1 scripts/demo.sh` lets the sign-in be clicked through.
- Parity: the synthetic mailbox yields identical pipeline results through the Gmail path and directly (tested).
- Found by the functional test, not by unit tests: Calendar was still hard-coded "not available" after Google was configured; signing in with a Google account whose email matched the development user crashed on a unique constraint (now: a verified email adopts an account never linked to Google, and refuses one linked to a different Google identity).
- Found by repetition: one store test picked "the first assertion" with no ordering and failed about one run in four when that row happened to be superseded. Fixed with a deterministic pick; the suite then passed seven consecutive runs.
- **What this does not prove:** that Google behaves as its documentation says. Nothing here has touched Google. The native sign-in path (`expo-web-browser` on a device) has not been run either.
- Not built, recorded in D57/D58: a retention window that purges stored bodies; propagation of deletions and label changes from Gmail.
- `scripts/verify.sh`: **ALL GREEN** — 252 backend/eval tests, 8 app tests, 126 functional checks (incl. the full sign-in → sync → ask → disconnect → sign-out journey against a separate fake-Google process); eval gate no regression across 24 scores.

**Slice 4 independent security review.** A fifth reviewer examined `ca3e753..13241d1` from a frozen snapshot with its own database. 2 high, 6 medium, 12 low, plus a list of likely surprises with real Google. Dispositions:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| H1 | high | Disconnecting Gmail mid-backfill was undone: a leftover queued page re-created the connection and re-read everything the user had just deleted | **Fixed.** Disconnect deletes pending syncs for that connection; background syncs never create a connection (`create=False`); at most one pending sync per connection. Test with a straggler job. |
| H2 | high | Outside `local` a signed-out user had no way to reach "Continue with Google": the only button lived behind an authenticated call | **Fixed.** Public `/auth/config`; a `SignedOut` screen shown on any 401, depending on nothing that needs a session; API errors carry their status. |
| M1 | med | Redirect allow-list matched by prefix (`pwm://auth.evil`, `exp://attacker…`), in every environment, leaking a live login code | **Fixed.** Exact match on scheme, host and path; no query or fragment; length-bounded; Expo Go's `exp://…/--/auth` only in `local`. 11 rejection cases tested. |
| M2 | med | The login code was bound to nothing: any app registered for `pwm://` could redeem it | **Fixed.** The app makes a secret, sends its SHA-256 with `/start`, and must present the secret to redeem. |
| M3 | med | Login CSRF: a link carrying an attacker's login code would sign the victim into the attacker's account | **Fixed by the same binding**: an app only redeems a code for a sign-in it started, and refuses when it holds no secret. |
| M4 | med | Permanently failed syncs stayed "syncing" forever; **no recurring sync existed at all** after sign-in; a stale page or sync token wedged the cursor; 403 rate limits were not retried | **Fixed.** `error` status with the exception class; `cli tick` queues due syncs every `PWM_SYNC_MINUTES`; stale Gmail page tokens restart the listing, Calendar 400 is treated like 410; 403 is retried. Tests for each. |
| M5 | med | Cancelled events stayed live and gained a duplicate; any non-time edit duplicated the event | **Fixed.** Only versions that say something new speak; a cancelled latest version silences the event; a bare `{id, status: cancelled}` deletion is stamped now. Test. The gold labels no longer expect the cancelled Denver conference as a fact (baseline updated: 25/30 facts, same five misses as before). |
| M6 | med | A missing or rotated key turned every read into a 500 and wedged processing; no key id existed despite the docstring; plaintext-era bodies were never re-sealed; with an unreadable token, delete-everything destroyed it locally and *said nothing* about the live grant at Google | **Fixed.** Reads use clear metadata and degrade gracefully; writes return 503 and change nothing; `enc:v2:<key id>:…`, `PWM_DATA_KEYS_OLD`, `cli reseal` (rotation tested end to end); `DELETE /me` reports `google_access_revoked`. |
| L1 | low | "A database dump does not contain anyone's mail" was overstated: quotes and values are in the clear | **Corrected** in code comments, `pwm.crypto`'s docstring and D57. |
| L2 | low | A state could be reused after a failed exchange | **Fixed.** Spent and committed before Google is called. Test. |
| L3 | low | Every token-endpoint 400/401 looked like "reconnect"; transport errors became 500s | **Fixed.** Only `invalid_grant` means the grant is gone. Test. |
| L4 | low | Duplicate follow-up chains | **Fixed** (one pending sync per connection; jobs are `running` while they run; stale running jobs are requeued). Long transaction around HTTP and whole-mailbox reprocessing per page: **open**, see below. |
| L5 | low | Forwarded/list mail with `dmarc=pass` was flagged forged | **Fixed.** DMARC pass wins; comments ignored. 7 cases tested. |
| L6–L8 | low | 500 on a long redirect; login codes never purged; a declined grant left alive at Google | **Fixed.** |
| L9–L12 | low | Code-state oracle; no rate limiting; sessionStorage readable by XSS; partial disconnect keeps the full grant | L9 fixed (one message). **Open:** rate limiting (belongs at the edge), web token storage (documented choice), partial disconnect keeps Gmail scope until Calendar goes too (D60; the app should say so). |

Also from the review, fixed before first contact with Google: drafts, spam and trash are never read (list query and label filter, including via history); HTML-only mail is read from its visible text with hidden elements removed; the calendar window is bounded at both ends so recurring events do not expand forever.

**Open, recorded deliberately:**
- Every page of a backfill re-runs the funnel over the whole mailbox: quadratic over a real 90-day read. Fine for 119 synthetic sources; needs incremental processing before a real inbox (also noted in D19).
- HTTP calls and backoff sleeps happen inside the job's transaction.
- Deletions and label changes in Gmail are not propagated; a body retention window is not built (D57, D58).
- In `local`, signing out appears to do nothing when the Google account's email is the development user's, because dev login serves the same adopted account.

**Expect these on first contact with real Google** (reviewer's list, none reproduced against Google): the fake accepts any redirect URI and client secret, always returns a refresh token and `scope`, and ignores `q` — so `newer_than:90d -in:draft` has never been exercised; whether a Calendar sync-token request may omit `singleEvents`; all-day events are pinned to UTC midnight; Workspace accounts without Gmail return 400 `failedPrecondition`; consent screen and test-user restrictions will surface as Google error pages.

- `scripts/verify.sh`: **ALL GREEN** — 275 backend/eval tests (suite repeated five times, stable), 8 app tests, 126 functional checks; eval gate no regression across 24 scores.
