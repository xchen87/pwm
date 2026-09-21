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
| Demo readiness — onboarding, connections/disconnect/delete, demo launcher and script, in-browser checks | built | commit `926d450` + next; verify green (122 tests, 87 functional checks incl. the built app in headless Chrome) |
| Slice 4 — accounts, real Gmail/Calendar | connector protocol, demo connector, Gmail/Calendar payload normalization built and tested; **OAuth, fetching, token storage, accounts need a Google OAuth client — founder** | commit `926d450` |
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

**Demo-readiness independent review.** Started over `00a624e..42d8ea7` (rewritten persistence, connections, Google normalization, model-backed writers, scheduled briefs, scripts, new app screens), including whether the earlier fixes actually hold. Findings and dispositions will be recorded below.

**Clean-checkout check.** Cloned the repository into a scratch directory, installed from the lockfiles only (`uv sync`, `npm ci`), and ran `scripts/verify.sh --quick`: **ALL GREEN** (161 tests, eval gate, app checks). One thing learned: `docker compose` in a differently named directory starts a second, unused database container; removed it. Also: selecting the model path without credentials now fails with a clear message, and provider failures reach the app as a generic 503 rather than a 500 (the provider's own error text can quote the request, so it is never passed on).
