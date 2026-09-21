#!/usr/bin/env bash
# The regression + functional gate. Run after every major step and before every commit.
# Usage: scripts/verify.sh [--quick]   (--quick skips the functional test, which includes the web build)
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
export PWM_ENVIRONMENT=local
step() { printf '\n== %s\n' "$1"; }

step "backend: format, lint, types"
uv run ruff format --check -q .
uv run ruff check -q .
uv run mypy | tail -1

step "database"
docker compose up -d --wait db >/dev/null 2>&1
uv run alembic upgrade head 2>&1 | tail -1
uv run alembic check | tail -1

step "backend + eval tests"
uv run pytest -q 2>&1 | tail -1

step "eval regression gate"
uv run python -m pwm_eval.check

step "app: types, lint, tests"
(cd app && npx tsc --noEmit && CI=1 npm run -s lint >/dev/null && npm test -s 2>&1 | grep -E "^Tests:")

if [[ "${1:-}" != "--quick" ]]; then
  step "functional: real server, real database, user journeys, the built app in a browser"
  uv run python scripts/functional_test.py
fi
printf '\nVERIFY: ALL GREEN\n'
