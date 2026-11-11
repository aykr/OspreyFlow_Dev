#!/usr/bin/env bash
# P12 part 1, round 3 (item 2): Laurium's own 3.13 environment at the head, offline, no stack: the
# laurium-service target's command (P12_MAKEFILE.diff, not applied on the branch), the 14 plants in
# that environment, and the strict xfail's four outcomes (p12_xfail_check.py). Run from OspreyFlow_Build
# under `scripts/stack_lease.sh offline case-b -- bash process/lanes/case-b/p12_laurium_offline.sh`.
set -u
BUILD="$(pwd)"; CORE="$BUILD/../OspreyFlow_Core"; ENV_DIR="$BUILD/laurium-env/.venv"
step() { echo; echo "=== $* ($(date -u +%H:%M:%SZ))"; }
step "laurium-env, by hash"
uv venv --python 3.13 --allow-existing "$ENV_DIR"
uv pip install --python "$ENV_DIR/bin/python" --require-hashes --only-binary :all: --no-deps -r "$CORE/services/laurium/requirements.txt"
uv pip install --python "$ENV_DIR/bin/python" --require-hashes --only-binary :all: --no-deps -r "$BUILD/tests/conformance/model_port/laurium_test_requirements.txt"
echo "laurium-env: exit $?"
cd "$CORE" || exit 1
step "laurium-service (the target's command)"
ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994 \
  "$ENV_DIR/bin/python" -m pytest -c "$BUILD/pytest.ini" -p no:cacheprovider -rA \
  ../OspreyFlow_Build/tests/conformance/model_port/test_laurium_service.py \
  ../OspreyFlow_Build/tests/conformance/model_port/test_suite_extract.py \
  ../OspreyFlow_Build/tests/conformance/model_port/test_laurium_findings_pending.py
echo "laurium-service: exit $?"
step "the plants in Laurium's environment"
PYTHONDONTWRITEBYTECODE=1 "$ENV_DIR/bin/python" ../OspreyFlow_Build/process/lanes/case-b/plants_P12.py --laurium "$ENV_DIR/bin/python"
echo "plants --laurium: exit $?"
step "the strict xfail, four outcomes"
PYTHONDONTWRITEBYTECODE=1 "$ENV_DIR/bin/python" ../OspreyFlow_Build/process/lanes/case-b/p12_xfail_check.py
echo "xfail check: exit $?"
