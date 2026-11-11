#!/usr/bin/env bash
# P12 round 2: Laurium's conforming-answer case twice more on the real gateway and pinned model (is
# the unparseable answer every time?), then what is left on the gateway. Same pair and lease.
set -u
export LITELLM_HOST=127.0.0.1 LITELLM_PORT=24000 LITELLM_API_KEY=sk-ospreyflow-dev
cd ../OspreyFlow_Core || exit 1
for i in 2 3; do
  echo "=== try $i"
  ../OspreyFlow_Build/laurium-env/.venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q \
    "../OspreyFlow_Build/tests/conformance/model_port/test_suite.py::test_extract_returns_data_conforming_to_the_requested_schema[extract_laurium]" \
    2>&1 | grep -E 'ExtractionFailedError:|passed|failed'
done
echo "=== left on the gateway"
curl -sS -H "Authorization: Bearer $LITELLM_API_KEY" \
  "http://$LITELLM_HOST:$LITELLM_PORT/key/list?return_full_object=true&size=100" \
  | python3 -c 'import json,sys; ks=json.load(sys.stdin)["keys"]; print("keys:", [(k.get("key_alias"), k.get("metadata")) for k in ks])'
curl -sS -H "Authorization: Bearer $LITELLM_API_KEY" "http://$LITELLM_HOST:$LITELLM_PORT/model/info" \
  | python3 -c 'import json,sys; print("models:", sorted(m["model_name"] for m in json.load(sys.stdin)["data"]))'
