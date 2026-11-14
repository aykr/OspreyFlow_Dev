#!/usr/bin/env bash
# Step B's load (DESIGN.md "The load", CALIBRATION.md): the client-size set at --scale 1 and
# --graph-scale 1.0, generated outside the checkout and loaded into the leased stack stage by stage,
# each timed; then the search index rebuilt from the graph and the drift check run. The stack is left
# loaded for step 4. Run from OspreyFlow_Core through
# `stack_lease.sh remote rules -- bash ../OspreyFlow_Build/process/lanes/rules/v052-load/load_b.sh`,
# which pins the leased stack's ports. A stage that fails stops the run; the loader's ledger resumes it.
set -euo pipefail
OUT="${LOAD_DIR:-$HOME/osprey-load/b-1.0}"
mkdir -p "$(dirname "$OUT")"
export PYTHONPATH=.:packages OSPREY_ANALYTICS_ENGINE=clickhouse
if [ ! -f "$OUT/manifest.json" ]; then
  echo "== generate ($(date -u +%FT%TZ))"
  /usr/bin/time -f "generate: %e s wall, %M KB max" .venv/bin/python -m scripts.generate_client_size \
    --out "$OUT" --scale 1 --graph-scale 1 --seed 20261116 --jobs 15
fi
du -sh "$OUT"
for stage in cases nodes edges same_as texts events check; do
  echo "== $stage ($(date -u +%FT%TZ))"
  /usr/bin/time -f "$stage: %e s wall" .venv/bin/python -m scripts.load_client_size --from "$OUT" --stages "$stage"
done
echo "== rebuild the search index ($(date -u +%FT%TZ))"
/usr/bin/time -f "rebuild: %e s wall, %M KB max" .venv/bin/python -m scripts.rebuild_search_index
echo "== drift check ($(date -u +%FT%TZ))"
set +e
/usr/bin/time -f "drift: %e s wall, %M KB max" .venv/bin/python -m scripts.search_index_drift
echo "drift exit=$?"
echo "== done ($(date -u +%FT%TZ))"
