#!/usr/bin/env bash
# One-command local dev: Docker → migrations → API + ARQ worker → account pipeline.
#
# Usage (via Make):
#   make up                              # boot services only
#   make up RIOT_ID='name#NA1'           # boot, then run the full pipeline for the account
#   make up RIOT_ID='name#NA1' COUNT=40 SKIP_LLM=1
#
# API and worker logs stream here with [api]/[worker] prefixes and are also
# written to .run/api.log and .run/worker.log. Ctrl-C stops everything.
# Written for macOS's bash 3.2: no associative arrays, no empty-array expansion.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
API_PORT=8000
RUN_DIR="$ROOT/.run"
API_PID=""
WORKER_PID=""

say() { printf '\033[1m[up]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[up] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# Prefix each line and append the raw line to a log file. awk (not sed -u)
# because BSD sed on macOS has no unbuffered flag.
prefix() {
  awk -v p="[$1] " -v f="$RUN_DIR/$1.log" \
    '{ print p $0; fflush(); print $0 >> f; fflush(f) }'
}

cleanup() {
  trap - INT TERM EXIT
  say "stopping services..."
  for pid in $API_PID $WORKER_PID; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  say "stopped"
}

# Exit from the handler itself; otherwise bash resumes the wait loop below and
# misreports a deliberate Ctrl-C as an unexpected service exit.
on_signal() {
  cleanup
  exit 130
}

# ── Preflight ────────────────────────────────────────────────────────
[ -x "$PY" ] || die ".venv missing — run 'make install' first"
[ -f services/api/.env ] || die "services/api/.env missing — copy services/api/.env.example"
docker info >/dev/null 2>&1 || die "Docker is not running — start Docker Desktop"
if command -v lsof >/dev/null 2>&1 && lsof -ti "tcp:$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  die "port $API_PORT is already in use — stop the other API (lsof -i :$API_PORT)"
fi
mkdir -p "$RUN_DIR"
: > "$RUN_DIR/api.log"
: > "$RUN_DIR/worker.log"

# ── Infra + migrations ───────────────────────────────────────────────
say "starting Postgres + Redis (waiting for healthchecks)..."
docker compose -f infra/compose/docker-compose.yml up -d --wait

say "applying migrations..."
(cd services/api && "$ROOT/.venv/bin/alembic" upgrade head)

# ── Long-running services ────────────────────────────────────────────
trap on_signal INT TERM
trap cleanup EXIT
export PYTHONUNBUFFERED=1

say "starting API on :$API_PORT and ARQ worker..."
"$ROOT/.venv/bin/uvicorn" --app-dir services/api main:app --reload \
  --host 0.0.0.0 --port "$API_PORT" > >(prefix api) 2>&1 &
API_PID=$!
(cd services/api && exec "$ROOT/.venv/bin/arq" app.services.background_jobs.WorkerSettings) \
  > >(prefix worker) 2>&1 &
WORKER_PID=$!

for _ in $(seq 1 60); do
  if curl -sf "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
    break
  fi
  kill -0 "$API_PID" 2>/dev/null || die "API exited during startup — see .run/api.log"
  sleep 1
done
curl -sf "http://localhost:$API_PORT/health" >/dev/null 2>&1 \
  || die "API not healthy after 60s — see .run/api.log"
say "API healthy"

# ── Account pipeline ─────────────────────────────────────────────────
if [ -n "${RIOT_ID:-}" ]; then
  say "running pipeline for $RIOT_ID..."
  # shellcheck disable=SC2086  # SKIP_LLM flag is intentionally word-split away when empty
  if "$PY" scripts/run_pipeline.py --riot-id "$RIOT_ID" --count "${COUNT:-20}" \
      ${SKIP_LLM:+--skip-llm} 2>&1 | prefix pipeline; then
    say "pipeline finished"
  else
    say "pipeline reported failures (services are still running)"
  fi
else
  say "no RIOT_ID given — skipping pipeline (make up RIOT_ID='name#NA1')"
fi

say "API http://localhost:$API_PORT · logs in .run/ · Ctrl-C to stop"
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WORKER_PID" 2>/dev/null; do
  sleep 2
done
say "a service exited unexpectedly — see .run/*.log"
exit 1
