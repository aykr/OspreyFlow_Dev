#!/usr/bin/env bash
# T1 part 4's leased run, from OspreyFlow_Build, as
#   scripts/stack_lease.sh acquire admin "<purpose>" && scripts/stack_lease.sh remote admin -- process/lanes/admin/t1/t1p4_run.sh
# on one commit and one lease, in order:
# 1. the isolation proof and its red (tests/test_worker_isolation_live.py);
# 2. the graph_port suite serial, then 4 and 8 workers: its wall time each way, and rule 3's access-control cases in it
#    passing unchanged in parallel;
# 3. test_route_rights.py (every leased run's), 4 workers then serial.
# Each step prints its exit and seconds; the script exits 1 if any step failed.
set -u
cd ../OspreyFlow_Core || exit 2
B=../OspreyFlow_Build
P=(.venv/bin/pytest -c "$B/pytest.ini" -q -rfE -p no:cacheprovider)
X=(-p tests.worker_isolation --dist loadgroup)
failed=0
step() {
  local name="$1" start rc
  shift
  start="$(date +%s)"
  "$@"
  rc=$?
  echo "STEP $name: exit $rc, $(( $(date +%s) - start )) s"
  [ "$rc" -eq 0 ] || failed=1
}
step isolation "${P[@]}" "$B/tests/test_worker_isolation_live.py"
step graph-serial "${P[@]}" "$B/tests/conformance/graph_port"
step graph-n4 "${P[@]}" "${X[@]}" -n 4 "$B/tests/conformance/graph_port"
step graph-n8 "${P[@]}" "${X[@]}" -n 8 "$B/tests/conformance/graph_port"
step rights-n4 "${P[@]}" "${X[@]}" -n 4 "$B/tests/services/api/test_route_rights.py"
step rights-serial "${P[@]}" "$B/tests/services/api/test_route_rights.py"
exit "$failed"
