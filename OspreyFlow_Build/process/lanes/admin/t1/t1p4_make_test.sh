#!/usr/bin/env bash
# T1 part 4, item 4: `make test`'s Python half serial and in parallel on one commit, offline, from OspreyFlow_Build, as
#   scripts/stack_lease.sh offline admin -- process/lanes/admin/t1/t1p4_make_test.sh [N …]
# Each run is the Makefile's own `test` target (its own --ignore list, SKIP_JS=1), with PYTEST overridden: first serial,
# then for each N (default `auto`) `-p tests.worker_isolation -n N --dist loadgroup`. Each prints its exit and seconds,
# then the nodeids whose outcome differs from the serial run's (xdist's `@group` suffix stripped), and the short
# traceback of each test that failed in either run; the script exits 1 if any set differs. Logs are kept in
# OSPREY_T1P4_LOGS (default: a temporary folder, printed) for reading afterwards.
set -u
B="$(pwd)"
out="${OSPREY_T1P4_LOGS:-$(mktemp -d)}"
mkdir -p "$out"
echo "LOGS $out"
base=".venv/bin/pytest -c $B/pytest.ini -q -p no:cacheprovider"
run() {
  local name="$1" start rc
  shift
  start="$(date +%s)"
  make -s test SKIP_JS=1 PYTEST="$base -rfE --tb=short $* --junitxml=$out/$name.xml" >"$out/$name.log" 2>&1
  rc=$?
  echo "RUN $name: exit $rc, $(( $(date +%s) - start )) s; $(tail -1 "$out/$name.log")"
  ../OspreyFlow_Core/.venv/bin/python - "$out/$name.xml" >"$out/$name.set" <<'PY'
import os, re, sys, xml.etree.ElementTree as ET
if not os.path.exists(sys.argv[1]):
    print("NO-JUNIT-FILE refused")
    sys.exit(0)
for case in ET.parse(sys.argv[1]).iter("testcase"):
    kinds = [c.tag for c in case if c.tag in ("failure", "error", "skipped")]
    name = re.sub(r"@[\w-]+$", "", case.get("name") or "")
    print(f"{case.get('classname')}::{name} {kinds[0] if kinds else 'passed'}")
PY
  sort -o "$out/$name.set" "$out/$name.set"
  awk '{print $2}' "$out/$name.set" | sort | uniq -c | tr '\n' ' '; echo
  grep -E "^(FAILED|ERROR) " "$out/$name.log" | sed "s/^/  $name /"
  grep -E "^(ERROR|E  )|UsageError" "$out/$name.log" | head -3 | sed "s/^/  $name says: /"
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
exit "$differs"
