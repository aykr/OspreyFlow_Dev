#!/usr/bin/env bash
# Step 4's runner shown red then green on a small leased stack, never d (the orchestrator's order, 14 November 2026).
# Run from the worktree root on the stack's own host:
#   OspreyFlow_Build/scripts/stack_lease.sh remote platform -- bash OspreyFlow_Build/process/lanes/platform/v052-measure/runner_proof.sh
# 1. Red: a case seeded for another principal; the runner's preflight must refuse it (m10-measure not granted) and not
#    run its command.
# 2. Green: a case seeded for m10-measure; the preflight must pass (and the probe, granted nothing, be refused), and the
#    command sees the OSPREY_MEASURE_* names (printed without their values).
# The graph is never dropped: each run seeds cases of its own name into what the stack holds. No token is printed.
set -uo pipefail
ROOT=$(pwd)
CORE=$ROOT/OspreyFlow_Core
PY=$CORE/.venv/bin/python
RUNNER=$ROOT/OspreyFlow_Build/process/lanes/platform/v052-measure/step4_stack.py
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
cd "$CORE" || exit 1
export PYTHONPATH=.:packages
A="http://127.0.0.1:${ARCADEDB_HTTP_PORT}/api/v1/server"
curl -s -o /dev/null -u "root:${ARCADEDB_ROOT_PASSWORD:-playwithdata123}" -X POST "$A" \
  -d '{"command":"create database ospreyflow"}' || true

# The images built once for both runs, and removed at the end.
TAG="step4-proof-$(echo "$STAMP" | tr 'A-Z' 'a-z')"
docker build -q -f services/api/Dockerfile -t "ospreyflow/api:$TAG" . >/dev/null || { echo "FAILED: the api image"; exit 1; }
docker build -q -f services/worker/Dockerfile -t "ospreyflow/worker:$TAG" . >/dev/null || { echo "FAILED: the worker image"; exit 1; }
export STEP4_API_IMAGE="ospreyflow/api:$TAG" STEP4_WORKER_IMAGE="ospreyflow/worker:$TAG"
trap 'docker rmi -f "ospreyflow/api:$TAG" "ospreyflow/worker:$TAG" >/dev/null 2>&1' EXIT

seed() {  # seed <principal> <unit> <name>: prints the case id
  "$PY" -m scripts.seed_fixture_corp --case-name "$3" --principal-id "$1" --org-unit "$2" >"/tmp/seed.$$" 2>&1 \
    || { tail -8 "/tmp/seed.$$"; echo "FAILED: seed for $1"; exit 1; }
  sed -nE "s/^Case '$3' is ([^ ]+)\.$/\1/p" "/tmp/seed.$$"
}

echo "# red: a case m10-measure is not granted"
OTHER=$(seed "step4-someone-else" unit-intel "Step 4 runner, not granted, $STAMP")
[ -n "$OTHER" ] || { echo "FAILED: no case id"; exit 1; }
"$PY" "$RUNNER" --case "$OTHER" -- sh -c 'echo "the command ran: the preflight let it"; exit 0'
red=$?
echo "# red: the runner's exit $red (2 is the preflight's refusal)"

echo "# green: a case seeded for m10-measure"
MINE=$(seed m10-measure unit-intel "Step 4 runner, granted, $STAMP")
[ -n "$MINE" ] || { echo "FAILED: no case id"; exit 1; }
"$PY" "$RUNNER" --case "$MINE" -- sh -c 'env | cut -d= -f1 | grep "^OSPREY_MEASURE_" | sort'
green=$?
echo "# green: the runner's exit $green"
left=$(docker ps -aq --filter "label=osprey.lane=${OSPREY_LANE:-platform}" | wc -l)
echo "# containers of this lane left after both runs: $left"
rm -f "/tmp/seed.$$"
[ "$red" -eq 2 ] && [ "$green" -eq 0 ] && [ "$left" -eq 0 ]
