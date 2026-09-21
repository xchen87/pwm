# Privacy and security threat model

Scope: the MVP — Gmail and Calendar read-only, explicit memories, a FastAPI backend on Postgres, and an Expo app on iOS, Android, and web. Reviewed at the end of every slice; a slice is not done until the rows it touches are updated.

Status values: **designed** (decided, not built), **built** (implemented and tested), **open** (needs a decision).

## What we hold and why it is sensitive

| Asset | Sensitivity |
|---|---|
| Google OAuth refresh tokens | Standing read access to a user's entire mailbox and calendar |
| Source records (metadata + verified quotes) | Private correspondence, including words written by people who never agreed to anything |
| Assertions (the world model) | A distilled profile of a person's life: more revealing than the raw mail |
| Session tokens on devices | Access to everything above through the API |
| Audit and eval logs | Can leak content if written carelessly |

## Threats

### T1. Prompt injection through email and calendar content
Anyone can email the user; every message is attacker-controlled text that a model will read. Goals: plant false commitments or decisions, alter or delete facts, mark things confirmed, exfiltrate data.

| Control | Status |
|---|---|
| Source text is delimited and labelled as data in every prompt | **built** (`extraction/prompts.py`); not yet exercised against a live model |
| Models that read source text have no tools and return schema-validated JSON only; output that fails validation is dropped | **built** (`anthropic_adapter.py`) |
| Quote verification drops candidates the source does not literally contain | **built** (`pwm.extraction.quotes`) |
| Verification runs against the visible text only: quoted replies, forwards, and hidden HTML are stripped first, so forged quotes and invisible instructions cannot supply evidence | **built** (`pipeline/text.py`; tested) |
| Sources with injection markers or a look-alike of the user are flagged; everything from them gets `low` confidence and a warning on the inspection screen | **built** |
| Pipeline output can never set `review`, trigger an action, or delete anything; `user_stated` is accepted only from user-capture sources | **built** (`pipeline/core.py` gate, `review.py` is the only writer; tested) |
| Adversarial fixture (10 attacks: instruction override, fake system text, hidden HTML, forged quoted replies, look-alike sender, JSON smuggling, deletion and exfiltration requests, mixed legitimate + injected) with a 100% pass bar | **built** (`fixtures/`, `eval/`) |
| Brief and Ask never take instructions from content: items are chosen by code, writers only word them, and Ask must cite evidence or decline | **built** (template writer/reasoner; a model-backed one must pass the same tests) |
| Low-confidence sources cannot answer questions, appear in a brief, or replace/dispute known facts | **built** (tested; the eval's planted question gets no answer) |

Residual risk: an injected sentence that is *itself* a literal quote ("Alex promised to pay $500") passes quote verification. That is why such items can only ever appear as "possible", with the sender and quote visible, and why sender trust (is this someone the user corresponds with?) feeds confidence in Slice 1.

### T2. Look-alike and spoofed senders
A message "from" the user or a known contact at a near-identical address (in the fixture: `examp1e-mail`). Control: entity resolution matches on exact address; display names never merge identities on their own (a merge also needs self-identification in the message, is stored as inferred, and can be split); nothing merges into the user; the user's own statements are accepted only through the app. Status: **built** (`pipeline/resolution.py`; tested). The first address seen founds a person and is the only one with authority; every address that joins later is a guess until the user confirms it, and authority is per link (D42, D46, D52): the independent review showed an impersonator could otherwise replace a trusted sender's facts. Remaining residual: a forged From header on the *same* address, to be closed with `Authentication-Results` in Slice 4.

### T2b. Forged From addresses
A message can claim any From. Control: Gmail's own verdict (`Authentication-Results`) is kept; failing DMARC, or both SPF and DKIM, marks the message suspicious — low confidence, unable to update or dispute anything, flagged on its inspection screen. Mail that merely claims the user's address without sitting in Sent does not make its recipient "known". Status: **built** (D59). Residual: a domain with no DMARC policy.

### T3. Third-party data
Correspondents did not consent to being modelled. Controls: message bodies are encrypted at rest under a key outside the database (D57; a retention window that purges them is designed, not built); do not infer relationship types, health, or other sensitive traits about third parties; deletion removes third-party data with the user's. Status: designed. **Open:** legal review of the privacy notice wording before the beta.

### T4. Model provider as sub-processor
Source text is sent to an external model API. Controls: provider disclosed to users; only models available under zero data retention and no-training terms may read source text; prompts and responses are not logged with content by us (token counts and versions only). Status: designed. **Open:** confirm provider terms per model before Slice 4 (`docs/decisions.md` D9).

### T5. OAuth token theft
Controls: refresh tokens exist only on the server, encrypted with AES-256-GCM under a key held outside the database, with the purpose bound in; read-only scopes; revoked at Google and destroyed on disconnect and on delete-everything; never sent to the device; Google errors carry a status code, never a body. Status: **built**, verified against a stand-in for Google only (D55, D57, D60).

### T6. Google API policy non-compliance
`gmail.readonly` is a restricted scope and Gmail-derived data falls under Google's Limited Use requirements: use only for prominent user-facing features, no transfer except to provide those features with user consent, and no human reading of user data without the user's agreement for specific messages (security and legal exceptions aside). Controls: no analytics or debugging workflow may expose message content to staff; support tooling shows metadata and IDs only. Status: designed. Verification status tracked in `docs/decisions.md` D15.

### T7. Lost or stolen phone
Controls: session token in the platform secure store (Keychain / Keystore via expo-secure-store; `sessionStorage` on the web, never `localStorage`); only its hash is stored server-side; sign-out revokes it; no source content persisted on the device. Status: **built**. Biometric lock: Slice 5.

### T8. Push notification leakage
Lock screens and notification services see payloads. Control: payloads are a fixed generic string plus a deep link; never names, amounts, dates, or quotes; an empty brief sends nothing. Status: **built** for the in-app inbox stand-in (`brief/service.py`; tested). Real push in Slice 5 implements the same `Notifier` and must reuse the same constant.

### T9. Embedded-webview OAuth phishing
Control: OAuth only through the system browser (`expo-web-browser` auth session) with PKCE and a deep link back (`pwm://`); app redirects are allow-listed; `state` is single-use and short-lived; the app receives a single-use code, never a token in a URL. Status: **built**; the native path has not been run on a device.

### T10. Incomplete deletion
"Delete my data" must remove sources, assertions, embeddings, brief items, and cached context, and revoke tokens. Controls: every derived row carries `source_id`; cascade is enforced by foreign keys and verified by a test that fails if any row survives. Status: cascade **built and tested** for sources and users (`test_store.py`); token revocation and the user-facing delete flow arrive in Slice 4. Backups: retention period to be set and disclosed — **open**.

### T11. Real data leaking into the repository or logs
Controls: `golden/` and `.env` are gitignored; fixtures are generated from a script containing only invented people on `.example` domains; the eval records scores, never content. Status: **built**. Logging rule: never log message bodies, quotes, or prompts; log IDs.

### T12. Secrets in the app bundle
Anything `EXPO_PUBLIC_*` ships to every user. Control: only the API base URL is public; all provider and Google credentials stay on the server. Status: **built** (documented in `docs/env.md`).

### T13. Cross-user access
Controls: every row carries `user_id`; handlers receive the user from one dependency and every lookup checks ownership (another user's assertion returns 404 — tested). Status: **built**. Requests carry a session token; without one, the local development user is served only when `PWM_ENVIRONMENT=local` and dev login is on, and everywhere else the answer is 401 (tested).

## Explicit non-goals for the MVP
End-to-end encryption with user-held keys, on-device extraction, and self-hosting. Each would strengthen the posture and each is incompatible with shipping the MVP; revisit after the beta.
