#!/usr/bin/env bash
# WS4a case 13: the workspace's budget gate run N times, each line with the machine's load and the commit.
# usage: perf_runs.sh <label> <n> [spec]
set -u
LABEL=$1; N=$2; SPEC=${3:-perf/perf.spec.ts}
OUT=$HOME/ws4a-tools/perf-$LABEL.log
: > "$OUT"
for i in $(seq 1 "$N"); do
  echo "== run $i of $N, $LABEL, $(git -C "$HOME/away-ws4a" rev-parse --short HEAD) (tree $(git -C "$HOME/away-ws4a" status --porcelain | wc -l) changed files), start $(date -u +%T), load $(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT"
  REPO=$HOME/away-ws4a bash "$HOME/osprey-d246/d246_ns.sh" env OSPREY_PORTS_SLOT=21 sh -c "cd apps/workspace && npx playwright test --config perf/playwright.config.ts $SPEC --workers=1 --reporter=line" > "$OUT.run$i" 2>&1
  echo "exit $?" >> "$OUT"
  grep -E "perf first frame|frame|passed|failed|Error|Timeout" "$OUT.run$i" | grep -v -E "rootlesskit|long-animation|LoAF" | cut -c1-300 >> "$OUT"
  echo "   end $(date -u +%T), load $(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT"
done
