#!/usr/bin/env bash
# Part C's leased live run (v052-selection, the orchestrator's stack g): the graph port's new conformance case on
# ArcadeDB (a one-type expand carries no trace of a hidden link of that type, ADR-098 Amendment 8, rule 3), red
# first by two plants in the ArcadeDB adapter's expand traversal (the access step on the link, and on its far end),
# then green; the preview's service cases; and test_route_rights.py (rule 4). Run from OspreyFlow_Build, under the
# lease, after `stack_lease.sh up case-b`:
#
#   scripts/stack_lease.sh remote case-b -- bash process/lanes/case-b/v052-selection/live_run.sh
#
# The plants are made in the server's own copy and put back; each step says its own exit code; nothing filtered.
set -u
BUILD="$(pwd)"
CORE="$BUILD/../OspreyFlow_Core"
step() { echo; echo "=== $* ($(date -u +%H:%M:%SZ))"; }
cd "$CORE" || exit 1
PYTEST=(.venv/bin/python -m pytest -c "$BUILD/pytest.ini" -p no:cacheprovider -rA)
CASE="$BUILD/tests/conformance/graph_port/test_suite.py::test_unauthorised_expand_by_type_matches_a_graph_without_the_hidden_links"
B=packages/adapters/graph_arcadedb/builders.py
EDGE_LINE='            f"repeat({edge_step}(){edge_filter}.{has_access}{temporal_filter}.as('"'"'e'"'"')"'
FAR_LINE='            f".{other_step}().{has_access}.simplePath())"'

# builders.py put back whatever ends the run (a plant's copy is beside it while it runs).
trap '[ -f "$B.orig" ] && mv "$B.orig" "$B"' EXIT INT TERM
verdict() {  # $1 what, $2 the exit code, $3 the exit code it must be
  if [ "$2" = "$3" ]; then echo "AS IT MUST BE: $1 (exit $2)"; else echo "NOT AS IT MUST BE: $1 (exit $2, must be $3)"; FAILED=1; fi
}
FAILED=0
# A suite that passes having run nothing is not a pass: its summary must count something passed.
ran() {  # $1 what, then the pytest arguments
  local what="$1" out rc; shift; out="$(mktemp)"
  "${PYTEST[@]}" "$@" 2>&1 | tee "$out"; rc=${PIPESTATUS[0]}
  if [ "$rc" = 0 ] && ! tail -3 "$out" | grep -q " passed"; then echo "NOT AS IT MUST BE: $what passed nothing"; FAILED=1; return; fi
  verdict "$what" "$rc" 0
}

plant() {  # $1 what, $2 the line as it stands, $3 the planted line
  step "plant: $1"
  cp "$B" "$B.orig"
  python3 - "$B" "$2" "$3" <<'PY'
import sys
path, old, new = sys.argv[1:4]
text = open(path).read()
assert text.count(old) == 1, "the line is not in builders.py exactly once"
open(path, "w").write(text.replace(old, new))
PY
  PYTHONPYCACHEPREFIX="$(mktemp -d)" "${PYTEST[@]}" "$CASE"
  verdict "planted: $1" $? 1
  mv "$B.orig" "$B"
}

step "1. the new conformance case on ArcadeDB, unplanted"
PYTHONPYCACHEPREFIX="$(mktemp -d)" "${PYTEST[@]}" "$CASE"
verdict "unplanted" $? 0

plant "the link's own access step left out" "$EDGE_LINE" '            f"repeat({edge_step}(){edge_filter}{temporal_filter}.as('"'"'e'"'"')"'
plant "the far end's access step left out" "$FAR_LINE" '            f".{other_step}().simplePath())"'

step "2. green again, put back"
echo "builders.py put back: $(grep -c "{edge_filter}.{has_access}{temporal_filter}.as('e')" "$B") line(s)"
PYTHONPYCACHEPREFIX="$(mktemp -d)" "${PYTEST[@]}" "$CASE"
verdict "after the plants" $? 0

step "3. the graph port's whole suite on ArcadeDB (nothing else moved)"
ran "the graph port suite" -q "$BUILD/tests/conformance/graph_port/test_suite.py"

step "4. the preview's service cases and the cap cases beside them"
ran "the preview's cases" -q "$BUILD/tests/services/api/working_set/test_preview_link_count.py" "$BUILD/tests/services/api/working_set/test_cap_counts_the_readers_view.py"

step "5. test_route_rights.py (rule 4)"
ran "test_route_rights.py" -q "$BUILD/tests/services/api/test_route_rights.py"
echo; [ "$FAILED" = 0 ] && echo "every step as it must be" || echo "a step NOT as it must be"
exit "$FAILED"
