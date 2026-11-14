#!/usr/bin/env bash
# Red first for the lease tests' own process table (case-b, 14 November 2026). Run from OspreyFlow_Build in a
# server copy (stack_lease.sh offline), where the reaping tests run (they need /proc and setsid). The script diff
# (stack_lease_sh.diff, the orchestrator's file) is applied for every step but those that name main's script; each
# plant is put back from the copy's HEAD. Offline: closed ports, no OSPREY_LANE. Every red keeps its assertion's words.
# The load steps take every core and add 2,000 processes on the shared host; each window is printed in UTC.
set -u
D=process/lanes/case-b/lease-tests
T=tests/test_stack_lease.py
ok=1
py() { (cd ../OspreyFlow_Core && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q -rf "../OspreyFlow_Build/$T" "$@" 2>&1); }
# OspreyFlow_Core/osprey-runs/ is stack_lease.sh's own: its npm step writes <lane>.meta/npm.lock relative to the
# copy's OspreyFlow_Core, not $HOME (reported to the orchestrator), so it is there before any step.
stray() {
  local left; left="$(git status --short -- .. | grep -vE ' (OspreyFlow_Build/)?(tests/test_stack_lease.py|scripts/stack_lease.sh)$' | grep -vxF '?? ../OspreyFlow_Core/osprey-runs/' | grep -vF "$D/" || true)"
  [ -z "$left" ] || { echo "LEFT IN THE COPY after $1:"; echo "$left"; ok=0; }
}
reasons() { grep -E "^FAILED|^E +(FileNotFoundError|AssertionError)" "$1" | sed -E 's|/tmp/pytest-of-[^ ]*/||; s/^(.{0,230}).*/\1/' | sort -u; }
verdict() { # name, want, log, for red: how many fail, and the words each failure must hold
  if [ "$2" = green ]; then
    if grep -qE "^FAILED|^ERROR|[0-9]+ failed|[0-9]+ errors?( |$)" "$3"; then echo "WRONG (something failed): $1"; reasons "$3"; ok=0; else echo "AS IT MUST BE (green): $1: $(grep -E '[0-9]+ passed' "$3" | tail -1)"; fi
  else
    if grep -qE "^=+ $4 failed|^$4 failed" "$3" && grep -qE "$5" "$3"; then echo "AS IT MUST BE (red): $1"; else echo "WRONG (not red as it must be): $1"; tail -3 "$3"; ok=0; fi
    reasons "$3"
  fi
}
load_on() { pids=(); for i in $(seq 1 2000); do sleep 900 & pids+=($!); done
  for i in $(seq 1 "$(nproc)"); do ( while :; do :; done ) & pids+=($!); done
  echo "load on at $(date -u +%H:%M:%SZ): processes $(ls -d /proc/[0-9]* | wc -l), burners $(nproc) of $(nproc) cores"; }
load_off() { kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null; echo "load off at $(date -u +%H:%M:%SZ)"; }
L=$(mktemp)
echo "copy head $(git rev-parse --short HEAD), on $(hostname), processes $(ls -d /proc/[0-9]* | wc -l), at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
FOUR='start_line or two_runs_named_alike or two_runs_of_one_lane'
WAITS='FileNotFoundError: .*/exit|still running'

# PLANTS_ONLY=1 skips step 0's load rounds (recorded once, in gates/plants-load.txt), so the shared host is loaded once.
if [ "${PLANTS_ONLY:-}" != 1 ]; then
# 0. Main as it is (its test file and its script), the host loaded as a night of lane runs loads it: every core and
#    2,000 more processes. Three rounds of the four exit-waiting cases; then the branch under the same load.
cp $D/main_test_stack_lease.py.txt $T  # main f5fe931's file, kept as .txt (the citation check reads .py files, and this one cites from tests/)
load_on
for r in 1 2 3; do py -k "$FOUR" --durations=4 > $L; echo "main, round $r: $(grep -E '[0-9]+ (passed|failed)' $L | tail -1)"; reasons $L; grep -E "s call" $L | sed 's/tests.test_stack_lease.py:://'; done
git checkout -q HEAD -- $T
git apply $D/stack_lease_sh.diff || { echo "the script diff does not apply"; exit 1; }
for r in 1 2 3; do py -k "$FOUR" --durations=4 > $L; echo "branch, round $r: $(grep -E '[0-9]+ (passed|failed)' $L | tail -1)"; reasons $L; grep -E "s call" $L | sed 's/tests.test_stack_lease.py:://'; done
py --durations=8 > $L
verdict "branch under the same load: the whole file" green $L
grep -E "s call" $L | sed 's/tests.test_stack_lease.py:://'
load_off
stray "the load rounds"
else git apply $D/stack_lease_sh.diff || { echo "the script diff does not apply"; exit 1; }
fi

# 1. The mechanism, planted: each run's table a large host's (8,000 entries, none of the run's) in place of the
#    empty one. The four wait on the scan of whatever table the run is given, and go red waiting.
python3 - "$T" <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
a='''        (tmp_path / "proc").mkdir(exist_ok=True)
        proc = str(tmp_path / "proc")'''
assert a in s, "the default table not found"
s=s.replace(a, '''        busy = tmp_path / "proc"
        for pid in range(4_000_000, 4_008_000):
            (busy / str(pid)).mkdir(parents=True, exist_ok=True)
            (busy / str(pid) / "environ").write_bytes(b"OSPREY_RUN_TAG=another-lane\\0")
        proc = str(busy)''')
open(p,"w").write(s)
PY
py -k "$FOUR" > $L
verdict "plant: every run's table a large host's" red $L 4 "$WAITS"
git checkout -q HEAD -- $T
stray "the large table"

# 2. Each reaping case given the empty table instead of /proc: red by its own words, so the default hides no reaping.
for name in test_a_run_reaps_a_server_that_left_its_process_group test_the_reaper_leaves_every_process_outside_the_run_alone test_a_runs_log_holds_no_error_of_the_reapers_own_reading; do
  python3 - "$T" "$name" <<'PY'
import sys; p,name=sys.argv[1],sys.argv[2]; s=open(p).read()
i=s.index(f"def {name}("); j=s.index("\ndef ", i+1)
body=s[i:j]; assert ", proc=REAL_PROC" in body, name
s=s[:i]+body.replace(", proc=REAL_PROC","")+s[j:]; open(p,"w").write(s)
PY
  py -k "$name" > $L
  verdict "plant: $name on the empty table" red $L 1 "outlived|Reaped 1 process"
  git checkout -q HEAD -- $T
  stray "$name on the empty table"
done

# 3. The table case: main's script (the scan reads /proc whatever it is given), then the diff with the re-read before
#    each signal reading the table (a listed pid signalled whatever real process holds it).
git checkout -q HEAD -- scripts/stack_lease.sh
py -k test_the_reaper_reads_the_process_table_it_is_given > $L
verdict "plant: main's script" red $L 1 "the scan read /proc"
git apply $D/stack_lease_sh.diff
python3 - scripts/stack_lease.sh <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
for a in ('for pid in $hit; do osprey_tagged "$pid" &&', 'if osprey_tagged "$pid"; then kill -9'):
    assert s.count(a)==1, a
    s=s.replace(a, a.replace('osprey_tagged "$pid"', 'osprey_tagged "$pid" "$root"'))
open(p,"w").write(s)
PY
py -k test_the_reaper_reads_the_process_table_it_is_given > $L
verdict "plant: the re-read before each signal reads the table" red $L 1 "the re-read read the table"
git checkout -q HEAD -- scripts/stack_lease.sh

# 4. The knob never reaching the host: cmd.sh's export line made to carry it.
git apply $D/stack_lease_sh.diff
python3 - scripts/stack_lease.sh <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
a="printf 'export OSPREY_RUN_TAG=$HOME/%s\\n' \"$run\""
assert s.count(a)==1, a
s=s.replace(a, a+"\n    printf 'export OSPREY_PROC_ROOT=%s\\n' \"${OSPREY_PROC_ROOT:-}\"")
open(p,"w").write(s)
PY
py -k test_remote_runs_the_command_on_the_stack_s_host_with_its_ports_and_lease > $L
verdict "plant: cmd.sh exports the caller's OSPREY_PROC_ROOT" red $L 1 "OSPREY_PROC_ROOT="
git checkout -q HEAD -- scripts/stack_lease.sh

rm -f $L
git status --short -- .. | grep -vF "$D/" | grep -vxF '?? ../OspreyFlow_Core/osprey-runs/' || true
[ $ok = 1 ] && echo "every plant red for its reason, unplanted green" || { echo "A PLANT WENT THE WRONG WAY"; exit 1; }
