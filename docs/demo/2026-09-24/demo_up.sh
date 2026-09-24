#!/usr/bin/env bash
# OspreyFlow demo bring-up — encodes docs/demo/2026-09-24/RUNBOOK.md's proven sequence.
#
#   ./docs/demo/2026-09-24/demo_up.sh --reset   # first time: empty ArcadeDB, seed HMP + Fixture Corp
#   ./docs/demo/2026-09-24/demo_up.sh           # later: restart services against the seeded data
#   ./docs/demo/2026-09-24/demo_up.sh --down    # stop Conduit, Glass and JWKS server (containers stay up)
#
# State (investigation id) lives OUTSIDE the repository in ~/.ospreyflow-demo/ so it can never be committed.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO"
STATE_DIR="$HOME/.ospreyflow-demo"; mkdir -p "$STATE_DIR"
STATE="$STATE_DIR/state.env"
LOG="$STATE_DIR"
PY=".venv/bin/python3"
export PYTHONPATH=.:packages
ARCADE_AUTH="root:playwithdata123"
JWKS_DIR="/tmp/dev-jwks"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

stop_host_services() {
  pkill -f 'uvicorn services.api.app' 2>/dev/null || true
  pkill -f 'vite' 2>/dev/null || true
  sleep 1
}

wait_for() { # wait_for <url> <label> <seconds>
  local url="$1" label="$2" n="${3:-60}"
  for ((i=0; i<n; i++)); do
    if curl -s -o /dev/null "$url"; then echo "    $label ready"; return 0; fi
    sleep 1
  done
  die "$label did not become ready at $url within ${n}s — see $LOG"
}

start_conduit() {
  say "Starting the Conduit on 127.0.0.1:8000"
  OIDC_JWKS_URL=http://localhost:8888/jwks.json \
    nohup .venv/bin/uvicorn services.api.app:app --host 127.0.0.1 --port 8000 \
    > "$LOG/conduit.log" 2>&1 &
  wait_for http://127.0.0.1:8000/openapi.json "Conduit" 90
}

if [[ "${1:-}" == "--down" ]]; then
  say "Stopping Conduit, Glass and JWKS server"
  stop_host_services
  pkill -f 'http.server 8888' 2>/dev/null || true
  echo "Done. Containers left running; 'make dev-down' stops them."
  exit 0
fi

[[ -x "$PY" ]] || die "project venv not found at $PY — run from the repository root after 'uv sync'"

say "Containers (make dev-up), then stopping the three model containers the demo does not need"
make dev-up
docker stop compose-ollama-1 compose-litellm-1 compose-speaches-1 >/dev/null 2>&1 || true

stop_host_services

if [[ "${1:-}" == "--reset" ]]; then
  say "Resetting ArcadeDB: drop + create database 'ospreyflow'"
  curl -s -u "$ARCADE_AUTH" -X POST http://localhost:2480/api/v1/server -d '{"command":"drop database ospreyflow"}' >/dev/null || true
  curl -s -u "$ARCADE_AUTH" -X POST http://localhost:2480/api/v1/server -d '{"command":"create database ospreyflow"}' >/dev/null
  rm -f "$STATE"
fi

say "Minting a fresh dev token (same throwaway key each time)"
mkdir -p "$JWKS_DIR"
TOKEN="$($PY -m scripts.mint_dev_token --jwks-path "$JWKS_DIR/jwks.json" | grep -E '^eyJ' | tail -1)"
[[ -n "$TOKEN" ]] || die "could not read a token from mint_dev_token's output"

if ! curl -s -o /dev/null http://localhost:8888/jwks.json; then
  say "Starting the JWKS server on :8888"
  nohup python3 -m http.server 8888 --directory "$JWKS_DIR" > "$LOG/jwks.log" 2>&1 &
  wait_for http://localhost:8888/jwks.json "JWKS server" 15
fi

start_conduit

if [[ -f "$STATE" ]]; then
  # shellcheck disable=SC1090
  source "$STATE"
  say "Reusing investigation $INV (from $STATE)"
else
  say "Creating the investigation"
  INV="$(curl -s -X POST http://127.0.0.1:8000/v1/investigations -H "Authorization: Bearer $TOKEN" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')"
  [[ -n "$INV" ]] || die "no investigation id returned — see $LOG/conduit.log"
  echo "INV=$INV" > "$STATE"
  echo "    Investigation: $INV"

  say "Stopping the Conduit so the seed scripts can take the DuckDB lock"
  pkill -f 'uvicorn services.api.app' || true; sleep 2

  say "Seeding the HMP fixture"
  $PY -m scripts.seed_hmp_fixture --investigation-scope "$INV"
  say "Seeding Fixture Corp"
  $PY -m scripts.seed_fixture_corp --investigation-scope "$INV"

  start_conduit
fi

say "Starting the Glass (Vite dev server)"
VITE_API_BASE_URL=http://127.0.0.1:8000 VITE_DEV_BEARER_TOKEN="$TOKEN" \
  nohup npm run dev --workspace apps/workspace > "$LOG/glass.log" 2>&1 &
wait_for http://localhost:5173 "Glass" 60

cat <<SUMMARY

================================================================================
 READY
   Glass:          http://localhost:5173/?investigation=$INV
                   (use localhost, not 127.0.0.1 — see RUNBOOK.md's own IPv6 finding)
   Investigation:  $INV
   Logs:           $LOG/{conduit,glass,jwks}.log

 Open the URL above directly — the Glass reads \`?investigation=\` on load and uses that
 investigation instead of creating its own (docs/02_GLASS_FRONTEND.md §2.1). No console step
 needed.

 Token expires in 8h. Re-run this script (without --reset) to re-mint and restart.
================================================================================
SUMMARY
