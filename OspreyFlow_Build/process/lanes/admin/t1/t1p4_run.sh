#!/usr/bin/env bash
# T1 part 4's leased run, from OspreyFlow_Build, as
#   scripts/stack_lease.sh acquire admin "<purpose>" && scripts/stack_lease.sh up admin &&
#   scripts/stack_lease.sh remote admin -- process/lanes/admin/t1/t1p4_run.sh [step …]
# on one commit and one lease, in order (or only the steps named; `clean` first removes what the live proof's first red
# run left on the shared names, `t1p4_clean.py`):
# 1. isolation: the live proof and its red (tests/test_worker_isolation_live.py);
# 2. graph: the graph_port suite serial, then at 4 and 8 workers, its wall time each way (its databases are per test,
#    so this measures the workers, not the redirect);
# 3. access: rule 3's live access-control files (every live file named for access control or a withheld read, which
#    open the redirected `ospreyflow`) and test_route_rights.py, serial then at 4 workers: the same pass and fail set.
# Each step prints its exit, its seconds, and each test's outcome (from its JUnit file), for comparing serial against
# parallel; the script exits 1 if any step failed.
set -u
cd ../OspreyFlow_Core || exit 2
B=../OspreyFlow_Build
P=(.venv/bin/pytest -c "$B/pytest.ini" -q -rfE -p no:cacheprovider)
X=(-p tests.worker_isolation --dist loadgroup)
out="$(mktemp -d)"
failed=0
step() {
  local name="$1" start rc
  shift
  start="$(date +%s)"
  "$@" --junitxml="$out/$name.xml"
  rc=$?
  echo "STEP $name: exit $rc, $(( $(date +%s) - start )) s"
  .venv/bin/python - "$out/$name.xml" "$name" <<'PY'
import sys, xml.etree.ElementTree as ET
rows = []
for case in ET.parse(sys.argv[1]).iter("testcase"):
    kinds = [c.tag for c in case if c.tag in ("failure", "error", "skipped")]
    rows.append(f"OUTCOME {sys.argv[2]} {kinds[0] if kinds else 'passed'} {case.get('classname')}::{case.get('name')}")
print("\n".join(sorted(rows)))
PY
  [ "$rc" -eq 0 ] || failed=1
}
access=(
  "$B/tests/services/api/test_route_rights.py"
  "$B/tests/adapters/graph_arcadedb/test_sources_withheld_live.py"
  "$B/tests/ingest/test_alert_evidence_withheld_live.py"
  "$B/tests/ingest/test_gazetteer_ids_withheld_live.py"
  "$B/tests/ingest/test_gazetteer_only_ids_withheld_everywhere_live.py"
  "$B/tests/ingest/test_node_preview_access.py"
  "$B/tests/resolve/test_projection_access_control.py"
  "$B/tests/services/api/test_access.py"
  "$B/tests/services/api/test_dossier_access_control.py"
  "$B/tests/services/api/test_investigation_access_store.py"
  "$B/tests/services/api/test_link_changes_withheld_live.py"
  "$B/tests/services/api/test_pid_access_control.py"
  "$B/tests/services/api/test_sources_withheld_routes.py"
  "$B/tests/services/api/working_set/test_compute_access_control.py"
  "$B/tests/services/api/working_set/test_connection_strength_access_control.py"
  "$B/tests/services/api/working_set/test_explain_cluster_access_control.py"
  "$B/tests/services/api/working_set/test_manual_resolution_access_control.py"
  "$B/tests/services/api/working_set/test_no_corpus_count_reveals_a_secret_link.py"
  "$B/tests/services/api/working_set/test_resolution_threshold_access_control.py"
)
steps=("$@")
[ "${#steps[@]}" -gt 0 ] || steps=(isolation graph access)
for s in "${steps[@]}"; do
  case "$s" in
    clean) PYTHONPATH="$B:.:packages" .venv/bin/python "$B/process/lanes/admin/t1/t1p4_clean.py" || failed=1 ;;
    isolation) step isolation "${P[@]}" "$B/tests/test_worker_isolation_live.py" ;;
    graph)
      step graph-serial "${P[@]}" "$B/tests/conformance/graph_port"
      step graph-n4 "${P[@]}" "${X[@]}" -n 4 "$B/tests/conformance/graph_port"
      step graph-n8 "${P[@]}" "${X[@]}" -n 8 "$B/tests/conformance/graph_port" ;;
    access)
      step access-serial "${P[@]}" "${access[@]}"
      step access-n4 "${P[@]}" "${X[@]}" -n 4 "${access[@]}" ;;
    *) echo "no step $s" >&2; exit 2 ;;
  esac
done
rm -rf "$out"
exit "$failed"
