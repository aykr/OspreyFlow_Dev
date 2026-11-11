#!/usr/bin/env bash
# P12 part 1, round 2: the leased live run (process/lanes/case-b/REPORT.md). Run from OspreyFlow_Build
# under `scripts/stack_lease.sh remote case-b -- bash process/lanes/case-b/p12_live_run.sh`, on the
# test server beside the orchestrator's pinned gateway pair (osprey-p12-gw-*, 11 November 2026):
# LiteLLM at CI's digest on 127.0.0.1:24000 with its own Postgres (virtual keys real), Ollama at CI's
# digest with the pinned conformance model. The master key is the repository's synthetic dev key.
#
# Each step runs whatever the one before it gave, and says its own exit code; nothing is filtered.
set -u
export LITELLM_HOST=127.0.0.1 LITELLM_PORT=24000 LITELLM_API_KEY=sk-ospreyflow-dev
export OSPREY_LIVE_GATEWAY_URL=http://127.0.0.1:24000 OSPREY_LIVE_GATEWAY_MASTER=sk-ospreyflow-dev
BUILD="$(pwd)"
CORE="$BUILD/../OspreyFlow_Core"
ENV_DIR="$BUILD/laurium-env/.venv"
step() { echo; echo "=== $* ($(date -u +%H:%M:%SZ))"; }

step "the gateway answers, and holds the conformance model"
curl -sS -o /dev/null -w "GET /health/liveliness: %{http_code}\n" "http://$LITELLM_HOST:$LITELLM_PORT/health/liveliness"
curl -sS -H "Authorization: Bearer $LITELLM_API_KEY" "http://$LITELLM_HOST:$LITELLM_PORT/v1/models" \
  | python3 -c 'import json,sys; print("models:", sorted(m["id"] for m in json.load(sys.stdin)["data"]))'

step "Laurium's own Python 3.13 environment, by hash (P12_MAKEFILE.diff's laurium-env)"
uv venv --python 3.13 --allow-existing "$ENV_DIR"
uv pip install --python "$ENV_DIR/bin/python" --require-hashes --only-binary :all: --no-deps \
  -r "$CORE/services/laurium/requirements.txt"
uv pip install --python "$ENV_DIR/bin/python" --require-hashes --only-binary :all: --no-deps \
  -r "$BUILD/tests/conformance/model_port/laurium_test_requirements.txt"
echo "laurium-env: exit $?"

cd "$CORE" || exit 1
PYTEST=(-m pytest -c "$BUILD/pytest.ini" -p no:cacheprovider -rA)
M="../OspreyFlow_Build/tests/conformance/model_port"

step "1. ModelPort's suite on Laurium (laurium_live_adapter), real gateway and pinned model, in Laurium's environment"
"$ENV_DIR/bin/python" "${PYTEST[@]}" "$M/test_suite.py" -k "laurium"
echo "suite on laurium: exit $?"

step "1b. the same suite's extract cases on the LiteLLM adapter, for comparison, in Laurium's environment"
"$ENV_DIR/bin/python" "${PYTEST[@]}" "$M/test_suite.py" -k "extract and litellm"
echo "suite extract on litellm: exit $?"

step "1c. Laurium's service cases and the extract refusals (stand-in over HTTP), in Laurium's environment"
"$ENV_DIR/bin/python" "${PYTEST[@]}" "$M/test_laurium_service.py" "$M/test_suite_extract.py"
echo "service and refusals: exit $?"

step "2. Laurium's key at the real gateway's admin routes, the Conduit's environment"
.venv/bin/python "${PYTEST[@]}" "$M/test_laurium_key_live.py"
echo "key live: exit $?"

step "2b. its plant at the adapter's call site, red"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/plants_P12.py --live
echo "plants --live: exit $?"

step "2c. green again after the plant is put back"
echo "adapter put back: $(grep -c "token = laurium_key(self._master)" packages/adapters/extract_laurium/adapter.py) line(s)"
.venv/bin/python "${PYTEST[@]}" "$M/test_laurium_key_live.py"
echo "key live after: exit $?"

step "what is left on the gateway: keys and models this run could have written"
curl -sS -H "Authorization: Bearer $LITELLM_API_KEY" \
  "http://$LITELLM_HOST:$LITELLM_PORT/key/list?return_full_object=true&size=100" \
  | python3 -c 'import json,sys; ks=json.load(sys.stdin)["keys"]; print("key aliases/metadata:", [(k.get("key_alias"), k.get("metadata")) for k in ks])'
curl -sS -H "Authorization: Bearer $LITELLM_API_KEY" "http://$LITELLM_HOST:$LITELLM_PORT/v1/models" \
  | python3 -c 'import json,sys; print("models:", sorted(m["id"] for m in json.load(sys.stdin)["data"]))'
