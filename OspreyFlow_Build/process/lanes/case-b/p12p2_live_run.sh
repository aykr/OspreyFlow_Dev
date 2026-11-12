#!/usr/bin/env bash
# P12 part 2's exit case, leased (process/lanes/case-b/P12p2_RED_RECORD.md): Laurium reading a conforming answer from a
# real model through the gateway, on the orchestrator's pinned pair beside the leased stack (LiteLLM at CI's digest
# with its own Postgres on the server's loopback 24000, Ollama with qwen2.5:7b-instruct, ADR-020 pin 845dbda0ea48).
# Run from OspreyFlow_Build under `scripts/stack_lease.sh remote case-b -- bash process/lanes/case-b/p12p2_live_run.sh`.
set -u
export LITELLM_HOST=127.0.0.1 LITELLM_PORT=24000 LITELLM_API_KEY=sk-ospreyflow-dev
BUILD="$(pwd)"; CORE="$BUILD/../OspreyFlow_Core"; ENV_DIR="$BUILD/laurium-env/.venv"
step() { echo; echo "=== $* ($(date -u +%H:%M:%SZ))"; }
step "the gateway, and the models it serves"
curl -sS -o /dev/null -w "liveliness: %{http_code}\n" "http://$LITELLM_HOST:$LITELLM_PORT/health/liveliness"
curl -sS -H "Authorization: Bearer $LITELLM_API_KEY" "http://$LITELLM_HOST:$LITELLM_PORT/v1/models" \
  | python3 -c 'import json,sys; print("models:", sorted(m["id"] for m in json.load(sys.stdin)["data"]))'
step "Laurium's environment, by hash"
uv venv --python 3.13 --allow-existing "$ENV_DIR" >/dev/null
uv pip install -q --python "$ENV_DIR/bin/python" --require-hashes --only-binary :all: --no-deps -r "$CORE/services/laurium/requirements.txt"
uv pip install -q --python "$ENV_DIR/bin/python" --require-hashes --only-binary :all: --no-deps -r "$BUILD/tests/conformance/model_port/laurium_test_requirements.txt"
echo "laurium-env: exit $?"
cd "$CORE" || exit 1
for model in qwen2.5:7b-instruct qwen2.5:0.5b-instruct; do
  step "the exit case on $model (three runs, each its own)"
  OSPREY_LAURIUM_LIVE_MODEL="$model" OSPREY_LAURIUM_TIMEOUT_SECONDS=600 OSPREY_MODEL_TIMEOUT_SECONDS=600 \
    "$ENV_DIR/bin/python" -m pytest -c "$BUILD/pytest.ini" -p no:cacheprovider -rA --durations=0 \
    ../OspreyFlow_Build/tests/conformance/model_port/test_laurium_reads_a_real_model_live.py
  echo "exit case on $model: exit $?"
done
step "what is left on the gateway"
curl -sS -H "Authorization: Bearer $LITELLM_API_KEY" \
  "http://$LITELLM_HOST:$LITELLM_PORT/key/list?return_full_object=true&size=100" \
  | python3 -c 'import json,sys; print("keys:", [(k.get("key_alias"), k.get("metadata")) for k in json.load(sys.stdin)["keys"]])'
