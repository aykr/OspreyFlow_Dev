#!/usr/bin/env bash
# The slice line's gate suite (slice-line/README.md, "Gates and their proofs"). Pure: no store, no network, no
# Claude session; it builds throwaway repositories under a temporary folder. Runs with its own checkout's
# OspreyFlow_Core venv (pytest, PyYAML), or the main checkout's (found through git) from a worktree without one.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MAIN="$(dirname "$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir)")"
TOP="$(git -C "$HERE" rev-parse --show-toplevel)"
# Its own checkout's venv where it has one (the merge gate's tree, built the CI way; CI's checkout), never the main
# checkout's then; a lane worktree with none uses the main checkout's.
if [ -n "${SLICE_LINE_PY:-}" ]; then PY="$SLICE_LINE_PY"
elif [ -x "$TOP/OspreyFlow_Core/.venv/bin/python" ]; then PY="$TOP/OspreyFlow_Core/.venv/bin/python"
else PY="$MAIN/OspreyFlow_Core/.venv/bin/python"; fi
cd "$HERE"
# The heartbeat (the owner, 25 November 2026; common.heartbeat): a line on standard error at least every 30 seconds while
# the suite runs, so a running suite is told from a stalled one. The merge's stall check never counts it as output.
beat() {
  local s=""
  trap 'kill "$s" 2>/dev/null || true; exit 0' TERM  # || true: under set -e a failed kill (the sleep just ended) exited 1
  local t0=$SECONDS
  while :; do
    sleep "${OSPREY_HEARTBEAT_SECONDS:-30}" & s=$!
    wait "$s"
    echo "[heartbeat $(date -u +%Y-%m-%dT%H:%M:%SZ)] tests/run.sh: the slice line's suite, $((SECONDS - t0)) s in" >&2
  done
}
beat & hb=$!
trap 'kill "$hb" 2>/dev/null || true; wait "$hb" 2>/dev/null || true' EXIT  # the suite's own exit stands, whatever the beat's
env PYTHONDONTWRITEBYTECODE=1 ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 "$PY" -m pytest -q -p no:cacheprovider -c "$HERE/pytest.ini" "$HERE" "$@"
