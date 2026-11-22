#!/usr/bin/env bash
# The early warning's own suite (DEMO_SERVER_EARLY_WARNING_BRIEF.md): the Mac side, the runner and its refusals, the
# named lists against this repository, the clean-up, and the scans of its own files. Pure: no network, no Docker, no
# server. Any python with pytest and PyYAML: EARLY_WARNING_PY, else this checkout's OspreyFlow_Core venv.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOP="$(git -C "$HERE" rev-parse --show-toplevel)"
PY="${EARLY_WARNING_PY:-$TOP/OspreyFlow_Core/.venv/bin/python}"
cd "$HERE"
exec env PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider -c "$HERE/pytest.ini" "$HERE" "$@"
