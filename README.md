# Personal World Model

## One-line thesis
A user-controlled model of your life that remembers what matters, understands what changed, and catches things before they become problems.

## Core idea
**One world model. Many experiences on top of it.**

The world model is a set of append-only, evidence-backed assertions about:
- people and your interactions with them
- things you own or pay for
- commitments (yours and other people's)
- decisions and their rationale
- events
- how all of these change over time

Every assertion keeps its source quote, how the system came to believe it, and whether *you* have confirmed it. Only you can confirm anything.

## MVP
Install the phone app, connect Gmail + Google Calendar, add explicit memories, and receive:
1. Commitment Radar
2. Your World — what changed, what needs attention
3. World Brief — in-app and by push notification
4. Ask Your World
5. Memory — remember this / correct this
6. Source inspection

Built last, and only once design-partner evidence supports them: passive Decision Memory and draft-only Customer Advocate.

## Product promise
> Connect your life. We'll remember what matters, tell you what changed, and catch things before they become problems.

## Stack
- **App:** Expo (React Native + TypeScript) — one codebase for iOS, Android, and web. Day-to-day development and testing run on a PC in a browser and emulator; the same code ships to phones.
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy/Alembic.
- **Data:** PostgreSQL only (pgvector, full-text search, jobs queue).
- **LLM:** behind narrow provider-agnostic interfaces, with frozen cacheable prompt prefixes.

## Repository structure

- `CLAUDE.md` — rules, scope, and approved stack for Claude Code
- `AGENT.md` — the single plan of record: vertical slices and acceptance criteria
- `TECHNICAL_BRIEF.md` — architecture, data model, trust model, evaluation
- `docs/` — decision log, architecture map, threat model, environment variables, local development
- `backend/` — FastAPI service, extraction interfaces, migrations
- `app/` — Expo app (iOS, Android, web)
- `eval/` — eval harness, metrics, score history, local golden-set labeller
- `fixtures/` — synthetic and adversarial fixture (generated; no real data, ever)
- `prompts/` — versioned prompt prefixes
- `investor_pitch.pptx` — investor/co-founder pitch (predates the current plan; where it differs, the documents above win)

Start with `docs/local-dev.md`.

## Status
Phase 0 is complete: scaffolding, fixture, adversarial set, eval harness with a recorded baseline, and the threat model. Nothing extracts yet — the baseline scores zero recall by design. Next is Slice 1, Commitment Radar.

## Build philosophy
The moat is not the foundation model. It is the persistent, temporal, user-controlled world model, plus provenance, permissions, trust, and action history.

Build in vertical slices: each one goes from source data to a screen on the phone to an eval score. Measure from day one — precision *and* recall, on noisy data, with an adversarial set.

## Immediate next actions
1. Conduct 30 discovery interviews; recruit 20 design partners.
2. Start Google OAuth verification for the restricted Gmail scope (long lead time).
3. Phase 0: scaffolding, noise-heavy synthetic fixture, adversarial fixture, eval harness with baseline scores.
4. Slice 1: Commitment Radar end to end, running in browser and emulator.
5. Slice 2: "What changed" and the World Brief.
