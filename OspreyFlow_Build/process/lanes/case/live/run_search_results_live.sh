#!/usr/bin/env bash
# v052-results' live check (ADR-145 Amendment 15 Part A against ADR-149's route), and any other live spec on the same
# set-up (LIVE_SEED, LIVE_SPECS below): live/search-results.spec.ts by default, on a leased stack's own host, with the Conduit and Vite there too, so nothing crosses the network from the Mac (the
# orchestrator, 14 November 2026). Run from the worktree root:
#   OspreyFlow_Build/scripts/stack_lease.sh remote case -- bash OspreyFlow_Build/process/lanes/case/live/run_search_results_live.sh
# The order is DEMO_GUIDE.md §3's, less its first Conduit: a token and its JWKS; Fixture Corp seeded into a case the
# seed makes (so the case reads its dataset, ADR-099); the search index rebuilt from the
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
mask() { sed -E "s#${TOKEN:-no-token-yet}#<token>#g; s#ticket=[A-Za-z0-9_-]+#ticket=<masked>#g"; }
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
# As a module from the Build root: it imports tests.conftest's signing (DEMO_GUIDE.md §2).
(cd ../OspreyFlow_Build && PYTHONPATH=.:../OspreyFlow_Core:../OspreyFlow_Core/packages "$PY" -m tools.mint_dev_token \
  --jwks-path "$W/jwks/jwks.json" >"$W/mint.txt" 2>"$W/mint.err") || { tail -5 "$W/mint.err"; fail "mint"; }
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
# The seed makes the case (`--case-name`) as analyst-1 of unit-1, the token's own account, so it is the case's first
# Author and the case reads Fixture Corp's dataset (scripts/case_seed.py's scope_for). The Conduit's POST
# /v1/investigations takes no empty body now (ADR-099 Amendment 12: a case names its one dataset).
# LIVE_SEED (default scripts.seed_fixture_corp) and LIVE_SPECS (default live/search-results.spec.ts) let the same
# set-up hold other live specs: scripts.seed_hmp_fixture for the scenario specs, which take the HMP fixture.
SEED=${LIVE_SEED:-scripts.seed_fixture_corp}
SPECS=${LIVE_SPECS:-live/search-results.spec.ts}
echo "# step: $SEED into a case the seed makes"
# A case of its own each run: the seed reuses a case of the same name, and the stack's Postgres keeps cases and their
# working sets between runs, so a second run's Show on graph found its records already there and sent nothing (the run
# at eb8a4ed). The graph is dropped above; the case's working set is not.
NAME="Live search check $(date -u +%Y%m%dT%H%M%SZ)"
"$PY" -m "$SEED" --case-name "$NAME" --principal-id analyst-1 --org-unit unit-1 >"$W/seed.txt" 2>&1
seeded=$?
mask <"$W/seed.txt" | tail -8
[ "$seeded" -eq 0 ] || fail "seed"
CASE=$(sed -nE "s/^Case '$NAME' is ([^ ]+)\.$/\1/p" "$W/seed.txt")
[ -n "$CASE" ] || fail "no case id in the seed's output"
echo "case: $CASE"
echo "# step: the search index rebuilt from the graph"
"$PY" -m scripts.rebuild_search_index 2>&1 | mask | tail -4
[ "${PIPESTATUS[0]}" -eq 0 ] || fail "rebuild"

echo "# step: the Conduit up, and the worker beside it to drain the index's outbox"
conduit_up second
# The seed's nodes sit in the graph's outbox until the indexer drains it, and every pending node is left out of every
# search (ADR-149's pending exclusion, ruling A), so a rebuild alone finds nothing (found by the run at 8ec9c33). The
# worker process drains it, as in a deployment; the spec starts once the route says its counts are exact (none
# pending), which assumes nothing about what it finds.
OSPREY_WORKER_NAME=case-live "$PY" -m services.api.worker_main >"$W/worker.log" 2>&1 &
pids+=($!)
drained=
for _ in $(seq 90); do
  exact=$(curl -s -X POST "http://127.0.0.1:$CP/v1/investigations/$CASE/search" -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -d '{"query":"QQ118439C","page":1,"page_size":20}' |
    "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("counts_exact"))' 2>/dev/null)
  [ "$exact" = True ] && { drained=1; break; }
  sleep 2
done
[ -n "$drained" ] || { tail -20 "$W/worker.log" | mask; fail "the outbox not drained in 180 s"; }
echo "# step: the outbox drained; the spec"
if [ "${LIVE_DIAG:-}" = 1 ]; then
  # Diagnosis only (LIVE_DIAG=1): the route asked directly, and what the index holds for one Person.
  for q in QQ118439C Volkov corp-res-identical-1; do
    printf '%s: ' "$q"
    curl -s -X POST "http://127.0.0.1:$CP/v1/investigations/$CASE/search" -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' -d "{\"query\":\"$q\",\"page\":1,\"page_size\":20}" |
      "$PY" -c 'import json,sys; b=json.load(sys.stdin); print({k: b.get(k) for k in ("total","counts_exact","source","limited","limited_reason","detail")}, [r["node_ids"] for r in b.get("results", [])][:3])'
  done
  curl -s "http://127.0.0.1:${OPENSEARCH_PORT}/ospreyflow-default/_search?q=type:Person&size=2" |
    "$PY" -c 'import json,sys; b=json.load(sys.stdin); print(b["hits"]["total"]); [print(json.dumps(h["_source"])[:900]) for h in b["hits"]["hits"]]'
  echo "== the case's datasets"
  curl -s "http://127.0.0.1:$CP/v1/investigations/$CASE/datasets" -H "Authorization: Bearer $TOKEN" | head -c 900; echo
  echo "== the index asked directly for the identifier"
  curl -s "http://127.0.0.1:${OPENSEARCH_PORT}/ospreyflow-default/_search?q=identifiers:QQ118439C&size=1" |
    "$PY" -c 'import json,sys; b=json.load(sys.stdin); print(b["hits"]["total"], [h["_id"] for h in b["hits"]["hits"]])'
  curl -s "http://127.0.0.1:${OPENSEARCH_PORT}/ospreyflow-default/_mapping" | head -c 1500; echo
  echo "== the case's own record"
  curl -s "http://127.0.0.1:$CP/v1/investigations/$CASE" -H "Authorization: Bearer $TOKEN" | head -c 900; echo
  grep -iE 'search|error|traceback' "$W/conduit.second.log" | mask | tail -15
  exit 0
fi
cd apps/workspace || exit 1
# Vite started here, as live/playwright.config.ts would, and warmed by one page load until the Glass draws its search
# box: a cold start's dependency build on a loaded host outlasted the first tests' timeouts (the run at 49093b4, three
# tests timing out on the box while the last passed). The spec then reuses this server (OSPREY_REUSE_SERVER=1).
echo "# load: $(cut -d' ' -f1-3 /proc/loadavg)"
VITE_API_BASE_URL="http://127.0.0.1:$CP" VITE_DEV_BEARER_TOKEN="$TOKEN" npx vite --port 5173 --strictPort >"$W/vite.log" 2>&1 &
pids+=($!)
for _ in $(seq 60); do curl -s -o /dev/null http://localhost:5173/ && break; sleep 1; done
started=$(date +%s)
CASE="$CASE" node -e '
const { chromium } = require("@playwright/test");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  // What the browser saw, said when the Glass does not draw: its console, page errors and failed or slow requests.
  const t0 = Date.now();
  const say = (m) => console.log(`[warm-up +${((Date.now() - t0) / 1000).toFixed(1)} s] ${m}`);
  page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") say(`console ${m.type()}: ${m.text().slice(0, 300)}`); });
  page.on("pageerror", (e) => say(`page error: ${String(e).slice(0, 300)}`));
  page.on("requestfailed", (r) => say(`request failed: ${r.url().slice(0, 160)} ${r.failure()?.errorText ?? ""}`));
  page.on("response", (r) => { if (r.status() >= 400) say(`response ${r.status()}: ${r.url().slice(0, 160)}`); });
  await page.goto(`http://localhost:5173/?investigation=${process.env.CASE}`);
  say("loaded");
  const box = page.locator(".top-bar [role=\"combobox\"]");
  await box.waitFor({ timeout: 240000 }).catch(async (e) => {
    say(`no search box; the body holds ${(await page.locator("body").innerText()).slice(0, 400).replace(/\s+/g, " ")}`);
    throw e;
  });
  say("search box drawn");
  // Through the results page too, so every module it loads has been asked for once, then a reload: what Vite finds to
  // bundle only on a later request reloads the page, and a page opened during that rebuild draws nothing.
  await box.fill("warm-up");
  await box.press("Enter");
  await page.locator("section.search-results").waitFor({ timeout: 600000 });
  await page.waitForTimeout(5000);
  await page.reload();
  await box.waitFor({ timeout: 600000 });
  await browser.close();
})().catch((e) => { console.error(String(e)); process.exit(1); });
' || { tail -20 "$W/vite.log" | mask; fail "the Glass did not draw its search box in 4 minutes"; }
echo "# warm-up: the Glass drew its search box after $(( $(date +%s) - started )) s"
OSPREY_REUSE_SERVER=1 OSPREY_TEST_LIVE_GLASS=1 OSPREY_LIVE_API_BASE_URL="http://127.0.0.1:$CP" OSPREY_LIVE_BEARER_TOKEN="$TOKEN" \
  OSPREY_LIVE_INVESTIGATION_ID="$CASE" \
  npx playwright test --config live/playwright.config.ts $SPECS --reporter=line 2>&1 | mask
code=${PIPESTATUS[0]}
echo "# playwright exit $code"
if [ "$code" -ne 0 ]; then
  echo "== Vite's log"
  grep -vE '^\s*$' "$W/vite.log" | mask | tail -30
  for f in test-results/*/error-context.md; do
    [ -f "$f" ] && { echo "== $f"; head -80 "$f" | mask; }
  done
  echo "== the last of the Conduit's log"
  tail -40 "$W/conduit.second.log" | mask
fi
exit "$code"
