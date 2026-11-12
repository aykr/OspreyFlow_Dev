#!/usr/bin/env bash
# P12 part 2, rebase for merge (the orchestrator's message of 12 November): on main eec25d1 with the five diffs applied,
# offline on the test server, no stack. Run from OspreyFlow_Build under
# `scripts/stack_lease.sh offline case-b -- bash process/lanes/case-b/p12p2_merge_gates.sh`.
# Each step runs whatever the last one gave; make test stops at its first failed line, so live-collect runs on its own.
set -u
BUILD="$(pwd)"
step() { echo; echo "=== $* ($(date -u +%H:%M:%SZ))"; }
step "head"; git -C "$BUILD" rev-parse HEAD 2>/dev/null || echo "(copied tree, no git)"
step "the three Laurium network files against the merged render"
( cd ../OspreyFlow_Core && .venv/bin/pytest -c "$BUILD/pytest.ini" -p no:cacheprovider -rA -q \
    ../OspreyFlow_Build/tests/harness/test_laurium_network_policy.py \
    ../OspreyFlow_Build/tests/harness/test_laurium_render.py \
    ../OspreyFlow_Build/tests/harness/test_laurium_cp_policy.py )
echo "laurium network files: exit $?"
step "cp-policy-check, unfiltered, every fixture"
make cp-policy-check
echo "cp-policy-check: exit $?"
step "make -k ci (OSPREY_PORTS_SLOT=14, harness-a11y included)"
OSPREY_PORTS_SLOT=14 make -k ci
echo "make -k ci: exit $?"
step "make test"
make test
echo "make test: exit $?"
step "make live-collect"
make live-collect
echo "make live-collect: exit $?"
step "done"
