#!/usr/bin/env bash
# rules-b am20's live gates, one run under the lease, from OspreyFlow_Core (the orchestrator's order,
# 14 November 2026): the new conformance file at the head; the rights table; red first against main's
# edges_among; the two live plants; the callers' suites; then the 50k rerun. Each part says its exit.
cd ../OspreyFlow_Core || exit 1
P=".venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q -rfE"
T=../OspreyFlow_Build/tests
echo "== START"; uptime; free -g
echo "== 1. the new conformance cases at the head"
$P -s $T/conformance/graph_port/test_edges_among_at_scale.py 2>&1 | grep -E "^ADR-124|passed|failed|^FAILED|^ERROR"; echo "exit ${PIPESTATUS[0]}"
echo "== 2. the rights table (a store test)"
$P $T/services/api/test_route_rights.py 2>&1 | grep -E "passed|failed|^FAILED|^ERROR"; echo "exit ${PIPESTATUS[0]}"
echo "== 3. red first, live, against main's edges_among"
.venv/bin/python ../OspreyFlow_Build/process/lanes/rules-b/am20/red_first_live.py
echo "== 4. the live plants"
.venv/bin/python ../OspreyFlow_Build/process/lanes/rules-b/am20/plants.py --live
echo "== 5. the callers' suites: the graph port's whole conformance, and the live files that call edges_among"
$P $T/conformance/graph_port $T/adapters/graph_arcadedb/test_sources_withheld_live.py \
   $T/services/api/working_set/test_link_weight_on_the_wire.py $T/services/api/test_batch_expansion_live.py \
   $T/ingest/test_run_writes_each_link_once_live.py $T/ingest/test_alert_evidence_withheld_live.py \
   $T/test_stamp_datasets.py $T/test_seed_links_replace.py $T/services/api/test_strength_sentence_rules.py \
   2>&1 | grep -E "passed|failed|^FAILED|^ERROR"; echo "exit ${PIPESTATUS[0]}"
echo "== 6. the 50k rerun"
PYTHONPATH=.:packages .venv/bin/python -u ../OspreyFlow_Build/process/lanes/rules-b/am20/measure50k_after.py; echo "exit $?"
echo "== END"; uptime; free -g
