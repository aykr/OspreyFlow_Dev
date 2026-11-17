#!/usr/bin/env bash
# The slice line's gate suite (slice-line/README.md, "Gates and their proofs"). Pure: no store, no network, no
# Claude session; it builds throwaway repositories under a temporary folder. Runs with the main checkout's
# OspreyFlow_Core venv (pytest, PyYAML), found through git so it works from any worktree.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MAIN="$(dirname "$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir)")"
PY="${SLICE_LINE_PY:-$MAIN/OspreyFlow_Core/.venv/bin/python}"
cd "$HERE"
exec env PYTHONDONTWRITEBYTECODE=1 ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 "$PY" -m pytest -q -p no:cacheprovider -c "$HERE/pytest.ini" "$HERE" "$@"
