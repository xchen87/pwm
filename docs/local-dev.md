# Local development

Everything runs on a PC. The app you open in the browser or emulator is the same code that ships to phones.

## Prerequisites
- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you)
- Node 22+
- Docker (for Postgres with pgvector)
- Optional: Android Studio emulator, or the Expo Go app on a phone

## Backend
```sh
uv sync                                   # create .venv and install dependencies
docker compose up -d --wait db            # Postgres + pgvector on localhost:5433
uv run alembic upgrade head               # apply migrations
uv run uvicorn pwm.api.main:app --reload  # API on http://localhost:8000
```

## App
```sh
cd app
npm install
npm run web        # browser, http://localhost:8081
npm run android    # Android emulator (set EXPO_PUBLIC_API_URL=http://10.0.2.2:8000)
npm start          # QR code for Expo Go on a physical phone
```

## Checks (run all of these before every commit)
```sh
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest
cd app && npm run typecheck && npm run lint && npm test
```

## Evaluation
```sh
uv run python -m pwm_eval.run                     # baseline on the synthetic fixture; appends to eval/results/history.jsonl
uv run python -m pwm_eval.run --system oracle --no-record   # sanity check: must be all 1.00
```

## Changing the fixture
Edit `fixtures/generate.py`, then `uv run python fixtures/generate.py`. A test fails if the committed JSON and the generator disagree, and another fails if any gold quote is not literally present in its source.

## Changing the API
```sh
uv run python -m pwm.api.export_openapi   # writes app/src/api/openapi.json
cd app && npm run gen:api                 # regenerates app/src/api/schema.d.ts
```

## Golden set (real mail, local only)
```sh
uv run python -m pwm_eval.golden ~/Downloads/takeout.mbox --limit 200
uv run python -m pwm_eval.run --fixture golden
```
Output goes to `golden/`, which is gitignored. Never copy anything from it into the repo, an issue, or a test.
