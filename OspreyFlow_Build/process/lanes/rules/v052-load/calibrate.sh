#!/usr/bin/env bash
# The calibration before step B's load (DESIGN.md "Wall time"): a set at --scale 0.02 and
# --graph-scale $GRAPH_SCALE (0.02, then 0.1, the stack reset between), generated outside the
# checkout and loaded into the leased stack, every stage timed, so B's load at --graph-scale 1.0 rests
# on measured rates, and the two points show whether the rate holds as the graph grows. Run from OspreyFlow_Core through
# `stack_lease.sh remote rules -- bash ../OspreyFlow_Build/process/lanes/rules/v052-load/calibrate.sh`,
# which pins the leased stack's ports. The stack is reset afterwards (reset_stack.py).
set -euo pipefail
GRAPH_SCALE="${GRAPH_SCALE:-0.1}"
OUT="${CALIBRATION_DIR:-$HOME/osprey-load/calibration-$GRAPH_SCALE}"
rm -rf "$OUT"
mkdir -p "$(dirname "$OUT")"
export PYTHONPATH=.:packages OSPREY_ANALYTICS_ENGINE=clickhouse
echo "== generate ($(date -u +%FT%TZ))"
/usr/bin/time -f "generate: %e s wall, %M KB max" .venv/bin/python -m scripts.generate_client_size \
  --out "$OUT" --scale 0.02 --graph-scale "$GRAPH_SCALE" --seed 20261116 --jobs 15
du -sh "$OUT"
for stage in cases nodes edges same_as texts events check; do
  echo "== $stage ($(date -u +%FT%TZ))"
  /usr/bin/time -f "$stage: %e s wall" .venv/bin/python -m scripts.load_client_size --from "$OUT" --stages "$stage"
done
echo "== done ($(date -u +%FT%TZ))"
