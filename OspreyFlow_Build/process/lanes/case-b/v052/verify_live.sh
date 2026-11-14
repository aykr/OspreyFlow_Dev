#!/usr/bin/env bash
# Step 6's verifier on R1's kind cluster (install_verify.py verify), with the environment platform's r1_kind.sh
# gives its own Python (its tools on the PATH, its kubeconfig, the kind platform's settings folder), so the kept
# render and the render check read as the install did. test_install_verify.py holds these three to r1_kind.sh's.
#
#   bash ../OspreyFlow_Build/process/lanes/case-b/v052/verify_live.sh [--candidate <commit>|auto] [--allow-pending]
#
# From OspreyFlow_Core, on the test server, under a lease, in the same copy as the upgrade or a later one with the
# same files. The candidate is `auto` unless named: the kept render's own commit, held to this copy's files.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GATES="$(cd "${OSPREY_V052_R1_GATES:-$HERE/../../platform/gates}" && pwd)"  # a plant's copy names the real one
STATE="$HOME/osprey-runs/platform.r1"
export PATH="$HOME/osprey-runs/platform.tools/bin:$PATH" KUBECONFIG="$STATE/kubeconfig"
export OSPREY_PLATFORM_FOLDERS="$(cd "$GATES/../../../.." && pwd)/tests/fixtures/cloud_platform/platforms"
case " $* " in *" --candidate "*) ;; *) set -- --candidate auto "$@" ;; esac
PYTHONPATH=.:packages:cli exec .venv/bin/python "$HERE/install_verify.py" verify "$@"
