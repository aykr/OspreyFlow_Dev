#!/usr/bin/env bash
# How long stack_lease.sh's own reaper takes on this host, for a tag no process carries, against how many
# processes the host has: what a run's EXIT trap costs before its exit file is written. Run from OspreyFlow_Build.
set -u
eval "$(python3 - <<'PY'
import re
s = open("scripts/stack_lease.sh").read()
m = re.search(r"^REAPER='(.*?)^}'", s, re.S | re.M)
print(m.group(1) + "}")
PY
)"
for i in 1 2 3; do
  n=$(ls -d /proc/[0-9]* 2>/dev/null | wc -l)
  t0=$(date +%s.%N); osprey_reap "/nonexistent/probe-$i" 2>/dev/null; t1=$(date +%s.%N)
  echo "processes $n, reap of an unused tag $(python3 -c "print(round($t1-$t0,2))") s"
done
# The same reap with the host as busy as a night of lane runs leaves it: 2,000 more processes (idle sleeps, so the
# cost measured is the scan, not CPU taken from it), ended before the probe exits.
if [ "${1:-}" = busy ]; then
  pids=(); for i in $(seq 1 2000); do sleep 120 & pids+=($!); done
  for i in 1 2; do
    n=$(ls -d /proc/[0-9]* 2>/dev/null | wc -l)
    t0=$(date +%s.%N); osprey_reap "/nonexistent/busy-$i" 2>/dev/null; t1=$(date +%s.%N)
    echo "busy: processes $n, reap of an unused tag $(python3 -c "print(round($t1-$t0,2))") s"
  done
  kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null
fi
