#!/usr/bin/env bash
# WS4a case 13 (I11's method): the React workspace's whole suite, as CI runs it, in one checkout.
# usage: suite_run.sh <label> <repo>
set -u
LABEL=$1; R=$2
OUT=$HOME/ws4a-tools/suite-$LABEL
mkdir -p "$OUT"
echo "== $LABEL at $(git -C "$R" rev-parse --short HEAD), start $(date -u +%T), load $(cut -d' ' -f1-3 /proc/loadavg)" > "$OUT/summary.log"
for step in "test" "test:keyboard" "test:a11y" "test:perf"; do
  echo "-- $step start $(date -u +%T) load $(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT/summary.log"
  REPO=$R bash "$HOME/osprey-d246/d246_ns.sh" env OSPREY_PORTS_SLOT=21 sh -c "npm run $step --workspace apps/workspace " > "$OUT/$step.log" 2>&1
  echo "   exit $? end $(date -u +%T)" >> "$OUT/summary.log"
  grep -E "^\s+[0-9]+ (passed|failed|flaky|skipped)|Tests\s+[0-9]|Test Files" "$OUT/$step.log" | sed 's/\x1b\[[0-9;]*m//g' >> "$OUT/summary.log"
done
echo "== end $(date -u +%T)" >> "$OUT/summary.log"
