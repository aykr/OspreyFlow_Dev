#!/usr/bin/env bash
# T1 part 4, item 4: `make test`'s Python half serial and in parallel on one commit, offline, from OspreyFlow_Build, as
#   scripts/stack_lease.sh offline admin -- process/lanes/admin/t1/t1p4_make_test.sh [N …]
# Each run is the Makefile's own `test` target (its own --ignore list, SKIP_JS=1), with PYTEST overridden: first serial,
# then for each N (default `auto`) `-p tests.worker_isolation -n N --dist loadgroup`. Each prints its exit and seconds,
# then the nodeids whose outcome differs from the serial run's, and the script exits 1 if any set differs.
set -u
B="$(pwd)"
out="$(mktemp -d)"
base=".venv/bin/pytest -c $B/pytest.ini -q -p no:cacheprovider"
run() {
  local name="$1" start rc
  shift
  start="$(date +%s)"
  make -s test SKIP_JS=1 PYTEST="$base $* --junitxml=$out/$name.xml" >"$out/$name.log" 2>&1
  rc=$?
  echo "RUN $name: exit $rc, $(( $(date +%s) - start )) s; $(tail -1 "$out/$name.log")"
  ../OspreyFlow_Core/.venv/bin/python - "$out/$name.xml" >"$out/$name.set" <<'PY'
import sys, xml.etree.ElementTree as ET
for case in ET.parse(sys.argv[1]).iter("testcase"):
    kinds = [c.tag for c in case if c.tag in ("failure", "error", "skipped")]
    print(f"{case.get('classname')}::{case.get('name')} {kinds[0] if kinds else 'passed'}")
PY
  sort -o "$out/$name.set" "$out/$name.set"
  awk '{print $2}' "$out/$name.set" | sort | uniq -c | tr '\n' ' '; echo
  grep -E "^(FAILED|ERROR) " "$out/$name.log" | sed "s/^/  $name /"
}
run serial
differs=0
counts=("$@")
[ "${#counts[@]}" -gt 0 ] || counts=(auto)
for n in "${counts[@]}"; do
  run "n$n" -p tests.worker_isolation -n "$n" --dist loadgroup
  if ! diff "$out/serial.set" "$out/n$n.set" >"$out/n$n.diff"; then
    differs=1
    echo "DIFF serial vs n$n:"; sed 's/^/  /' "$out/n$n.diff"
  else
    echo "SAME serial vs n$n: $(wc -l <"$out/serial.set") outcomes"
  fi
done
rm -rf "$out"
exit "$differs"
