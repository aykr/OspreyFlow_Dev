#!/usr/bin/env bash
# The calibration before step B's load (DESIGN.md "Wall time"): a set at --scale 0.02 and
# --graph-scale 0.02, generated outside the checkout and loaded into the leased stack, every stage
# timed, so the real load's size rests on measured rates. Run from OspreyFlow_Core through
# `stack_lease.sh remote rules -- bash ../OspreyFlow_Build/process/lanes/rules/v052-load/calibrate.sh`,
# which pins the leased stack's ports. The stack is reset afterwards (reset_stack.py).
set -euo pipefail
OUT="${CALIBRATION_DIR:-$HOME/osprey-load/calibration-0.02}"
rm -rf "$OUT"
mkdir -p "$(dirname "$OUT")"
export PYTHONPATH=.:packages OSPREY_ANALYTICS_ENGINE=clickhouse
echo "== generate ($(date -u +%FT%TZ))"
/usr/bin/time -f "generate: %e s wall, %M KB max" .venv/bin/python -m scripts.generate_client_size \
  --out "$OUT" --scale 0.02 --graph-scale 0.02 --seed 20261116 --jobs 15
du -sh "$OUT"
for stage in cases nodes edges same_as texts events check; do
  echo "== $stage ($(date -u +%FT%TZ))"
  /usr/bin/time -f "$stage: %e s wall" .venv/bin/python -m scripts.load_client_size --from "$OUT" --stages "$stage"
done
echo "== done ($(date -u +%FT%TZ))"
