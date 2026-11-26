#!/usr/bin/env bash
# The early warning's own suite (DEMO_SERVER_EARLY_WARNING_BRIEF.md): the Mac side, the runner and its refusals, the
# named lists against this repository, the clean-up, and the scans of its own files. Pure: no network, no Docker, no
# server. Any python with pytest and PyYAML: EARLY_WARNING_PY, else this checkout's OspreyFlow_Core venv.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOP="$(git -C "$HERE" rev-parse --show-toplevel)"
PY="${EARLY_WARNING_PY:-$TOP/OspreyFlow_Core/.venv/bin/python}"
cd "$HERE"
# The heartbeat (the owner, 25 November 2026; common.heartbeat): a line on standard error at least every 30 seconds while
# the suite runs, so a running suite is told from a stalled one. The merge's stall check never counts it as output.
beat() {
  local s=""
  trap 'kill "$s" 2>/dev/null; exit 0' TERM
  local t0=$SECONDS
  while :; do
    sleep "${OSPREY_HEARTBEAT_SECONDS:-30}" & s=$!
    wait "$s"
    echo "[heartbeat $(date -u +%Y-%m-%dT%H:%M:%SZ)] demo_server/tests/run.sh: the early warning's suite, $((SECONDS - t0)) s in" >&2
  done
}
beat & hb=$!
trap 'kill "$hb" 2>/dev/null; wait "$hb" 2>/dev/null' EXIT
env PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider -c "$HERE/pytest.ini" "$HERE" "$@"
