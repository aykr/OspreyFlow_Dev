#!/usr/bin/env bash
# rules-b am20's live run 2: the chunk-boundary case's fixture fixed (5fea6b5), so the new conformance
# file again at the head, then the two live plants and their control, each red with its reason.
cd ../OspreyFlow_Core || exit 1
echo "== START"; uptime; free -g
echo "== 1. the new conformance cases at the head"
.venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q -s -rfE ../OspreyFlow_Build/tests/conformance/graph_port/test_edges_among_at_scale.py 2>&1 | grep -E "^ADR-124|passed|failed|^FAILED|^ERROR|^E "; echo "exit ${PIPESTATUS[0]}"
echo "== 2. the live plants"
.venv/bin/python ../OspreyFlow_Build/process/lanes/rules-b/am20/plants.py --live
echo "== END"; uptime; free -g
