#!/usr/bin/env bash
# Start the whole demo on this machine: database, synthetic mailbox, API, and the app in a browser.
#   scripts/demo.sh            start empty, at "Connect your life" (wipes the local demo user first)
#   scripts/demo.sh --loaded   start with the demo mailbox already connected and a brief ready
#   scripts/demo.sh --keep     keep everything exactly as you left it last time
# No API key and no real mailbox are involved: extraction is the rule-based stand-in.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
# The synthetic mailbox lives in September 2026. Pin the clock there so dates read sensibly.
export PWM_FIXED_NOW="${PWM_FIXED_NOW:-2026-09-12T09:00:00+00:00}"
export PWM_EXTRACTOR="${PWM_EXTRACTOR:-heuristic}"
API_PORT="${API_PORT:-8000}"
APP_PORT="${APP_PORT:-8081}"

for port in "$API_PORT" "$APP_PORT"; do
  if ss -ltn 2>/dev/null | grep -q ":$port "; then
    echo "Port $port is already in use. Stop whatever is using it, or set API_PORT / APP_PORT." >&2
    exit 1
  fi
done

docker compose up -d --wait db >/dev/null
uv run alembic upgrade head 2>&1 | tail -1
case "${1:-}" in
  --keep) ;;
  --loaded)
    uv run python -m pwm.cli reset
    uv run python -m pwm.cli demo
    uv run python -m pwm.cli brief
    ;;
  *) uv run python -m pwm.cli reset ;;
esac

uv run uvicorn pwm.api.main:app --port "$API_PORT" --log-level warning &
API_PID=$!
# Stop only what this script started, never the whole process group.
trap 'kill "$API_PID" 2>/dev/null || true' EXIT
(cd app && [[ -d node_modules ]] || npm install --no-audit --no-fund >/dev/null)
echo
echo "  App:  http://localhost:$APP_PORT   (API on :$API_PORT, demo clock $PWM_FIXED_NOW)"
echo "  Walkthrough: docs/demo-script.md        Stop: Ctrl+C"
echo
cd app && EXPO_PUBLIC_API_URL="http://localhost:$API_PORT" BROWSER=none npx expo start --web --port "$APP_PORT"
