#!/usr/bin/env bash
# v052-results' live check (ADR-145 Amendment 15 Part A against ADR-149's route): live/search-results.spec.ts on a
# leased stack's own host, with the Conduit and Vite there too, so nothing crosses the network from the Mac (the
# orchestrator, 14 November 2026). Run from the worktree root:
#   OspreyFlow_Build/scripts/stack_lease.sh remote case -- bash OspreyFlow_Build/process/lanes/case/live/run_search_results_live.sh
# The order is DEMO_GUIDE.md §3's: a token and its JWKS; the Conduit up to make the case; the Conduit down; Fixture
# Corp seeded into that case (the seed makes the case read its dataset, ADR-099); the search index rebuilt from the
# graph (ADR-150 decision 4); the Conduit up again; the spec. The graph database is dropped and made again first, as
# §3.1 says, because the throwaway stack may hold an earlier run's records. Neither the token nor a port is printed.
set -uo pipefail
ROOT=$(pwd)
CORE=$ROOT/OspreyFlow_Core
export PATH=$HOME/.local/node/bin:$PATH
W=$(mktemp -d)
pids=()
cleanup() {
  for p in "${pids[@]}"; do kill "$p" 2>/dev/null; done
  wait 2>/dev/null
  rm -rf "$W"
}
trap cleanup EXIT
cd "$CORE" || exit 1
PY=$CORE/.venv/bin/python
export PYTHONPATH=.:packages
free_port() { "$PY" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'; }
mask() { sed "s#${TOKEN:-no-token-yet}#<token>#g"; }
fail() {
  echo "FAILED: $1"
  for f in "$W"/conduit.*.log; do [ -f "$f" ] && { echo "== the last of ${f##*/}"; tail -40 "$f" | mask; }; done
  exit 1
}

echo "# step: the graph database made fresh"
A="http://127.0.0.1:${ARCADEDB_HTTP_PORT}/api/v1/server"
AUTH="root:${ARCADEDB_ROOT_PASSWORD:-playwithdata123}"
curl -s -o /dev/null -u "$AUTH" -X POST "$A" -d '{"command":"drop database ospreyflow"}'
curl -sf -o /dev/null -u "$AUTH" -X POST "$A" -d '{"command":"create database ospreyflow"}' || fail "create database"

echo "# step: a token and its JWKS (analyst-1, unit-1, OFFICIAL, role analyst)"
mkdir -p "$W/jwks"
"$PY" ../OspreyFlow_Build/tools/mint_dev_token.py --jwks-path "$W/jwks/jwks.json" >"$W/mint.txt" 2>/dev/null || fail "mint"
TOKEN=$(tail -1 "$W/mint.txt")
JP=$(free_port)
"$PY" -m http.server "$JP" --bind 127.0.0.1 --directory "$W/jwks" >/dev/null 2>&1 &
pids+=($!)

CP=$(free_port)
export OIDC_JWKS_URL="http://127.0.0.1:$JP/jwks.json" CORS_ALLOWED_ORIGINS=http://localhost:5173 \
  OPENSEARCH_HOST=127.0.0.1 ANALYTICS_DB_PATH="$W/analytics.duckdb"
CPID=
conduit_up() {
  "$CORE/.venv/bin/uvicorn" services.api.app:app --host 127.0.0.1 --port "$CP" >"$W/conduit.$1.log" 2>&1 &
  CPID=$!
  pids+=("$CPID")
  for _ in $(seq 120); do
    curl -sf -o /dev/null "http://127.0.0.1:$CP/healthz" && return 0
    kill -0 "$CPID" 2>/dev/null || fail "the Conduit ($1) exited"
    sleep 1
  done
  fail "the Conduit ($1) not healthy in 120 s"
}
conduit_down() { kill "$CPID" 2>/dev/null; wait "$CPID" 2>/dev/null; }

echo "# step: the Conduit up, the case made"
conduit_up first
CASE=$(curl -sf -X POST "http://127.0.0.1:$CP/v1/investigations" -H "Authorization: Bearer $TOKEN" | "$PY" -c 'import json, sys; print(json.load(sys.stdin)["id"])') || fail "make the case"
echo "case: $CASE"
conduit_down

echo "# step: Fixture Corp seeded into the case"
"$PY" -m scripts.seed_fixture_corp --investigation-scope "$CASE" 2>&1 | mask | tail -8
[ "${PIPESTATUS[0]}" -eq 0 ] || fail "seed"
echo "# step: the search index rebuilt from the graph"
"$PY" -m scripts.rebuild_search_index 2>&1 | mask | tail -4
[ "${PIPESTATUS[0]}" -eq 0 ] || fail "rebuild"

echo "# step: the Conduit up again; the spec"
conduit_up second
cd apps/workspace || exit 1
OSPREY_TEST_LIVE_GLASS=1 OSPREY_LIVE_API_BASE_URL="http://127.0.0.1:$CP" OSPREY_LIVE_BEARER_TOKEN="$TOKEN" \
  OSPREY_LIVE_INVESTIGATION_ID="$CASE" \
  npx playwright test --config live/playwright.config.ts live/search-results.spec.ts --reporter=line 2>&1 | mask
code=${PIPESTATUS[0]}
echo "# playwright exit $code"
if [ "$code" -ne 0 ]; then
  echo "== the last of the Conduit's log"
  tail -40 "$W/conduit.second.log" | mask
fi
exit "$code"
