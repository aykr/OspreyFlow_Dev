#!/usr/bin/env bash
# v0.6.0 stage 2: search measured again on B's load at client size (ADR-149 Amendment 2's M1, M3-M6, M9, M10),
# each step one command, run on stack d's host by stack_lease.sh remote from the worktree root:
#
#   OspreyFlow_Build/scripts/stack_lease.sh remote <lane> -- bash OspreyFlow_Build/process/lanes/v060/stage2/run.sh <step>
#
# Steps, in the sheet's order (process/lanes/v060/STAGE2_SHEET.md): inputs, budgets, m9, leaks, never-join,
# control, table; profile and regen only when the sheet says. Every step but inputs and table runs inside
# platform's step 4 runner (step4_stack.py: Keycloak with step 4's subjects, the Conduit and the worker at the
# poc's limits, the preflight), as step 4 and its rerun did on 14 November. Results go to $STAGE2_OUT (default
# ~/osprey-load/stage2), one folder per step, never over an earlier one.
#
# STAGE2_SHORT=1 is the rehearsal: the same commands with n 10 after 2 (M1, M3-M5), M6 at 3 draws after 5,
# M10 on its files' first 20 cases, the profilers at their least; results under ~/osprey-load/stage2-rehearsal.
# A short run's figures are not measurements.
set -euo pipefail
STEP=${1:?usage: run.sh inputs|regen|budgets|m9|leaks|never-join|control|profile|table}
CASE=01M7C2SXAPP3RF8QRSR2SKEMJK            # B's Intelligence reports case, as step 4 measured it
LOAD=$HOME/osprey-load
QUERIES=$LOAD/step4/queries.jsonl
LEAKS=$LOAD/m10/leaks.jsonl
NEVER_JOIN=$LOAD/m10/never_join.jsonl
OPENSEARCH=osprey-test-d-opensearch       # M9 stops this one, d's own, and starts it again
SHORT=${STAGE2_SHORT:-0}
if [ "$SHORT" = 1 ]; then OUT=${STAGE2_OUT:-$LOAD/stage2-rehearsal}; else OUT=${STAGE2_OUT:-$LOAD/stage2}; fi
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../../../../../OspreyFlow_Core"
MEASURE=../OspreyFlow_Build/process/lanes/platform/v052-measure
RUNNER=(.venv/bin/python "$MEASURE/step4_stack.py" --case "$CASE" --)
PYTEST=(.venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -rfs
        ../OspreyFlow_Build/tests/perf/test_search_budget_live.py)
fresh() {  # a step's results folder, never one already written
  local d="$OUT/$1"
  if [ -e "$d" ]; then echo "$d exists: a step's results are never written over; move it aside first" >&2; exit 2; fi
  mkdir -p "$d"; echo "$d"
}
short_file() {  # the rehearsal's first 20 cases of an M10 file
  local f="$OUT/inputs/$(basename "$1")"; mkdir -p "$OUT/inputs"; head -20 "$1" > "$f"; echo "$f"
}
summary() {
  for f in "$1"/M*.json; do
    [ -e "$f" ] || continue
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print({k: d.get(k) for k in ("measure","class","n","p50_ms","p95_ms","max_ms","budget_ms","cases","reached","reach_bound","reached_on_page","verdict")})' "$f"
  done
}
echo "stage 2 step $STEP, $( [ "$SHORT" = 1 ] && echo "SHORT (rehearsal, not a measurement)" || echo "official" ), $(date -u +%FT%TZ), run copy $(git -C .. log -1 --format=%h 2>/dev/null || echo '?'), results $OUT"
case "$STEP" in
  inputs)
    # The inputs step 4 measured (14 November); a different hash means a different measurement.
    sha256sum "$QUERIES" "$LEAKS" "$NEVER_JOIN"
    printf '%s\n' "expected: f564f75f… queries.jsonl, ae02aa9c… leaks.jsonl, 48af1d50… never_join.jsonl"
    wc -l "$LEAKS" "$NEVER_JOIN" | head -2
    docker ps --format '{{.Names}} {{.Status}}' | grep -E '^osprey-test-d-' ;;
  regen)
    # Only if scripts/client_size_leaks.py has changed since 14 November (the sheet). Writes a new folder; the
    # files in use are replaced by hand, after the counts are read.
    d=$(fresh m10-regen)
    PYTHONPATH=.:packages .venv/bin/python -m scripts.client_size_leaks --from "$LOAD/b-1.0" --out "$d" \
      --limit "$( [ "$SHORT" = 1 ] && echo 20 || echo 500 )" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print("counts:", {k: d[k] for k in ("leaks_eligible","leaks_kept_out","never_text_dropped","leaks_words")})'
    sha256sum "$d"/*.jsonl ;;
  budgets)
    d=$(fresh budgets)
    if [ "$SHORT" = 1 ]; then export OSPREY_MEASURE_N=10 OSPREY_MEASURE_WARMUP=2 OSPREY_MEASURE_LAG_N=3; fi
    OSPREY_MEASURE_QUERIES=$QUERIES OSPREY_MEASURE_RESULTS=$d \
      "${RUNNER[@]}" "${PYTEST[@]}" -k "not m9 and not m10" || rc=$?
    summary "$d"; exit "${rc:-0}" ;;
  m9)
    d=$(fresh m9)
    OSPREY_MEASURE_QUERIES=$QUERIES OSPREY_MEASURE_STOP_OPENSEARCH=$OPENSEARCH OSPREY_MEASURE_RESULTS=$d \
      "${RUNNER[@]}" "${PYTEST[@]}" -k m9 || rc=$?
    summary "$d"; docker ps --format '{{.Names}} {{.Status}}' | grep "^$OPENSEARCH"; exit "${rc:-0}" ;;
  leaks|never-join)
    d=$(fresh "m10-$STEP")
    f=$( [ "$STEP" = leaks ] && echo "$LEAKS" || echo "$NEVER_JOIN" )
    [ "$SHORT" = 1 ] && f=$(short_file "$f")
    OSPREY_MEASURE_QUERIES=$QUERIES OSPREY_MEASURE_LEAKS=$f OSPREY_MEASURE_RESULTS=$d \
      "${RUNNER[@]}" "${PYTEST[@]}" -k m10 || rc=$?
    summary "$d"; exit "${rc:-0}" ;;
  control)
    # The words check shown to fire (rule 15): 5 hidden reports' titles searched as their cleared control.
    OSPREY_MEASURE_LEAKS=$LEAKS "${RUNNER[@]}" .venv/bin/python ../OspreyFlow_Build/process/lanes/rules/m10-query/positive_control.py ;;
  profile)
    # Diagnosis only, when a figure is over its budget (the sheet): read-only, one page of each kind timed in
    # process and over the wire, and M9's graph fallback query beside its variants.
    names=$(python3 -c 'import json,sys; q=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]; print("\n".join([x["query"] for x in q if x["class"]=="names"][:5]))' "$QUERIES")
    mapfile -t NAMES <<< "$names"
    "${RUNNER[@]}" .venv/bin/python "$MEASURE/profile_page.py" --database ospreyflow --queries "$QUERIES" \
      --repeat "$( [ "$SHORT" = 1 ] && echo 2 || echo 10 )" --warm "$( [ "$SHORT" = 1 ] && echo 1 || echo 2 )"
    PYTHONPATH=.:packages .venv/bin/python "$MEASURE/profile_m9.py" --database ospreyflow \
      --repeat "$( [ "$SHORT" = 1 ] && echo 1 || echo 3 )" "${NAMES[@]}" ;;
  table)
    # ADR-149 Amendment 2's table from the steps' results (M10's row from the leaks file; never-join's verdict
    # is read from its own folder).
    all=$(fresh table); cp "$OUT"/budgets/M*.json "$OUT"/m9/M*.json "$OUT"/m10-leaks/M*.json "$all"/
    .venv/bin/python "$MEASURE/results_table.py" --results "$all" --stack d --commit "$(git -C .. log -1 --format=%h 2>/dev/null)"
    echo "never-join:"; summary "$OUT/m10-never-join" ;;
  *) echo "unknown step $STEP" >&2; exit 2 ;;
esac
