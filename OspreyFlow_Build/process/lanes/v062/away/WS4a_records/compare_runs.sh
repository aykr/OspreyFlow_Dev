#!/usr/bin/env bash
# WS4a: the canvas-look comparison run N times, each run's per-scene shares recorded with the load and the commit.
# usage: compare_runs.sh <label> <n> [extra playwright args]
set -u
LABEL=$1; N=$2; shift 2; EXTRA="$*"
OUT=$HOME/ws4a-tools/compare-$LABEL.log
: > "$OUT"
for i in $(seq 1 "$N"); do
  echo "== run $i of $N, $LABEL, $(git -C "$HOME/away-ws4a" rev-parse --short HEAD) (tree $(git -C "$HOME/away-ws4a" status --porcelain | wc -l) changed files), start $(date -u +%T), load $(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT"
  REPO=$HOME/away-ws4a bash "$HOME/osprey-d246/d246_ns.sh" env OSPREY_PORTS_SLOT=21 sh -c "cd apps/workspace && npx playwright test --config keyboard/canvas-compare.config.ts --workers=1 --reporter=line $EXTRA" > "$OUT.run$i" 2>&1
  echo "exit $?" >> "$OUT"
  grep -E "canvas-compare |passed|failed|flaky|Error:|✘|  [0-9]+\) " "$OUT.run$i" | grep -v rootlesskit | cut -c1-260 >> "$OUT"
  echo "   end $(date -u +%T), load $(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT"
done
