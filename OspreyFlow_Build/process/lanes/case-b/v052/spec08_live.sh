#!/usr/bin/env bash
# Spec 08 on poc (spec08_poc.py run) on R1's kind cluster, with the environment platform's r1_kind.sh gives its own
# Python: its tools on the PATH (kubectl, docker), its kubeconfig and the kind platform's settings folder, as
# verify_live.sh gives install_verify.py. `r1_kind.sh py` cannot run it: it hands its arguments to r1_kind.py's own
# argparse. test_install_verify.py holds these three to r1_kind.sh's.
#
#   bash ../OspreyFlow_Build/process/lanes/case-b/v052/spec08_live.sh [pytest arguments]
#
# From OspreyFlow_Core, on the test server, under a lease, after the install.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GATES="$(cd "${OSPREY_V052_R1_GATES:-$HERE/../../platform/gates}" && pwd)"  # a plant's copy names the real one
STATE="$HOME/osprey-runs/platform.r1"
export PATH="$HOME/osprey-runs/platform.tools/bin:$PATH" KUBECONFIG="$STATE/kubeconfig"
export OSPREY_PLATFORM_FOLDERS="$(cd "$GATES/../../../.." && pwd)/tests/fixtures/cloud_platform/platforms"
PYTHONPATH=.:packages:cli exec .venv/bin/python "$HERE/spec08_poc.py" run "$@"
