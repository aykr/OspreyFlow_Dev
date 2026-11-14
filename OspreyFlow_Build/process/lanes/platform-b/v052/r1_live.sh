#!/usr/bin/env bash
# Step 6's own scripts on R1's kind cluster, with the environment platform's r1_kind.sh gives its own Python
# (its tools on the PATH, so its pinned kubectl; its kubeconfig; the kind platform's settings folder) and the
# checkout's Python, as case-b's verify_live.sh gives install_verify.py. `r1_kind.sh py` runs r1_kind.py
# alone, and a bare `python` would use whatever kubectl and ~/.kube/config the host has (the orchestrator's
# review of v052-r1, must 3). tests/test_v052_dashboards_check.py holds these to r1_kind.sh's by running both.
#
#   bash ../OspreyFlow_Build/process/lanes/platform-b/v052/r1_live.sh dashboards run
#   bash ../OspreyFlow_Build/process/lanes/platform-b/v052/r1_live.sh survival snap|verify
#   bash ../OspreyFlow_Build/process/lanes/platform-b/v052/r1_live.sh spec08 run
#
# From OspreyFlow_Core, on the test server, in the copy the row names (the run sheet).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GATES="$(cd "${OSPREY_V052_R1_GATES:-$HERE/../../platform/gates}" && pwd)"  # a test names a copy
STATE="$HOME/osprey-runs/platform.r1"
export PATH="$HOME/osprey-runs/platform.tools/bin:$PATH" KUBECONFIG="$STATE/kubeconfig"
export OSPREY_PLATFORM_FOLDERS="$(cd "$GATES/../../../.." && pwd)/tests/fixtures/cloud_platform/platforms"
case "${1:-}" in
  dashboards) script="$HERE/dashboards_check.py" ;;
  survival) script="$HERE/survival.py" ;;
  spec08) script="$(cd "$GATES/../../case-b/v052" && pwd)/spec08_poc.py" ;;
  *) echo "r1_live.sh: dashboards run | survival snap|verify | spec08 run" >&2; exit 2 ;;
esac
shift
PYTHONPATH=.:packages:cli exec .venv/bin/python "$script" "$@"
