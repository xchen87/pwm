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
| Slice 2 — What changed + World Brief | built (backend + app); **independent review in progress** | commit `00a624e`; verify green |
| Slice 3 — Ask Your World + Remember / Correct / Forget | built (backend + app); **independent review in progress** | commit `00a624e`; verify green |
| Demo readiness — onboarding, connections/disconnect/delete, demo launcher and script, in-browser checks | built | commit `926d450` + next; verify green (122 tests, 87 functional checks incl. the built app in headless Chrome) |
| Slice 4 — accounts, real Gmail/Calendar | connector protocol, demo connector, Gmail/Calendar payload normalization built and tested; **OAuth, fetching, token storage, accounts need a Google OAuth client — founder** | commit `926d450` |
| Slice 5 — phone builds, real push | not started; store/TestFlight builds **need founder** (Expo / Apple / Google accounts) | |
| Live LLM evaluation | blocked: **needs founder** (API key + spend approval) | |

## Waiting on the founder
These do not block the demo-ready goal, but nothing can replace them:
1. **Google Cloud project + restricted-scope verification** (decisions D15). Long lead time; gates the beta, not the demo.
2. **Golden set**: label ~200 threads of your own mail with `uv run python -m pwm_eval.golden <mbox>`. The only honest benchmark.
3. **Model API key + spend approval** for `pwm_eval.run --system anthropic --allow-spend`. Until then every score comes from the rule-based stand-in and says nothing about real-world quality.

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

**Slices 2–3 independent review.** Started over `02c1c86..00a624e`. Findings and dispositions will be recorded below.
