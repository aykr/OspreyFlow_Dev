#!/usr/bin/env bash
# The search index's catch-up after step B's load (ADR-150 decision 2; the orchestrator's request,
# 14 November): the product's own indexer, as a deployment runs it (the worker process,
# `python -m services.api.worker_main`, which feeds the index where an OpenSearch is configured, one
# replica under a Valkey lease), until both outboxes are empty. Every 30 s the outboxes' sizes are
# printed with the time, so the record gives the catch-up's length and its rows a second; then the
# worker is stopped with SIGTERM (its own handler) and the drift check is run. Run from OspreyFlow_Core
# through `stack_lease.sh remote rules -- bash ../OspreyFlow_Build/process/lanes/rules/v052-load/drain_index.sh`.
set -uo pipefail
HERE=../OspreyFlow_Build/process/lanes/rules/v052-load
export PYTHONPATH=.:packages OSPREY_ANALYTICS_ENGINE=clickhouse
# A lane stack has no identity provider, and the worker takes the API's whole config, which refuses to
# start without a JWKS URL though the indexer never resolves a principal. A deployment always has one;
# here a placeholder on a closed port (the orchestrator's ruling, 14 November): test-environment
# configuration, never fetched by the indexer. The product change is a CARRIES row.
export OIDC_JWKS_URL="${OIDC_JWKS_URL:-http://127.0.0.1:9/jwks}"
count() { .venv/bin/python "$HERE/outbox_count.py"; }
echo "== before ($(date -u +%FT%TZ)): $(count)"
.venv/bin/python -m services.api.worker_main > "$HOME/osprey-load/worker.log" 2>&1 &
WORKER=$!
START=$(date +%s)
while kill -0 "$WORKER" 2>/dev/null; do
  sleep 30
  NOW=$(count) || NOW="unreadable"
  echo "$(date -u +%FT%TZ) +$(( $(date +%s) - START ))s: $NOW"
  if [ "$NOW" = "graph 0 text 0" ]; then
    echo "== drained in $(( $(date +%s) - START )) s"
    break
  fi
done
if ! kill -0 "$WORKER" 2>/dev/null; then
  echo "== the worker stopped on its own: its log follows"
  tail -40 "$HOME/osprey-load/worker.log"
  exit 1
fi
kill -TERM "$WORKER"; wait "$WORKER"; echo "worker exit=$?"
grep -iE "search index|feeding" "$HOME/osprey-load/worker.log" | tail -5
echo "== drift check ($(date -u +%FT%TZ))"
/usr/bin/time -f "drift: %e s wall, %M KB max" .venv/bin/python -m scripts.search_index_drift
echo "drift exit=$?"
