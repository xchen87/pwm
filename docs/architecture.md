# Architecture

The full rationale is in `TECHNICAL_BRIEF.md`. This page is the map.

```mermaid
flowchart TD
    subgraph Sources["Sources — untrusted input"]
        G[Gmail read-only]
        C[Google Calendar read-only]
        U[Explicit user capture]
    end

    G & C & U --> CONN[Connectors]
    CONN --> SRC[(Source records — immutable)]

    subgraph Funnel["Funnel pipeline — Postgres jobs queue"]
        F1[1 prefilter — code]
        F2[2 thread assembly — code]
        F3[3 triage — cheap model]
        F4[4 extraction — model, no tools]
        F5[5 quote verification — code]
        F6[6 entity resolution — code first]
        F7[7 temporal reconciliation — code]
        F8[8 confidence — code]
        F1 --> F2 --> F3 --> F4 --> F5 --> F6 --> F7 --> F8
    end

    SRC --> F1
    F8 --> WM[(World model — append-only assertions)]
    WM --> RET[Retrieval: SQL, as-of, pgvector, recursive CTEs]
    RET --> API[FastAPI — OpenAPI contract]
    API --> APP[Expo app: iOS, Android, web]
    APP -->|confirm / dismiss / correct — the only path to 'confirmed'| WM

    EVAL[Eval harness] -. runs the same pipeline on fixtures .-> Funnel
```

## Code layout

| Path | Contents |
|---|---|
| `backend/src/pwm/sources.py` | `SourceRecord`: what connectors produce and the pipeline consumes |
| `backend/src/pwm/extraction/` | `Candidate` schema, the `Extractor` protocol, quote verification |
| `backend/src/pwm/api/` | FastAPI app and OpenAPI export |
| `backend/migrations/` | Alembic migrations |
| `eval/pwm_eval/` | gold label schema, metrics, systems under test, runner, golden-set labeller |
| `fixtures/generate.py` | deterministic generator for `fixtures/synthetic/` |
| `app/` | Expo app; `src/api/schema.d.ts` is generated from the backend's OpenAPI schema |

## Boundaries that must hold

- Business logic imports `pwm.extraction.interface`, never a model provider's SDK.
- The app imports generated API types, never hand-written ones. `backend/tests/test_openapi_contract.py` fails when the committed schema is stale.
- A system under evaluation receives sources and the user's identity — never gold labels.
- Nothing but a user action writes `review`.
