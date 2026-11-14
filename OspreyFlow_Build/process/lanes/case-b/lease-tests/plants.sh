#!/usr/bin/env bash
# Red first for the lease tests' own process table (case-b, 14 November 2026). Run from OspreyFlow_Build in a
# server copy (stack_lease.sh offline), where the reaping tests run (they need /proc and setsid). The script diff
# (stack_lease_sh.diff, the orchestrator's file) is applied for every step but the one that leaves it out; each plant
# is put back from the copy's HEAD. Offline: closed ports, no OSPREY_LANE.
set -u
D=process/lanes/case-b/lease-tests
T=tests/test_stack_lease.py
ok=1
py() { (cd ../OspreyFlow_Core && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q "../OspreyFlow_Build/$T" "$@" 2>&1); }
stray() { # what a step left in the copy outside its own plant: nothing, or it is named
  local left; left="$(git status --short -- .. | grep -vE ' (OspreyFlow_Build/)?(tests/test_stack_lease.py|scripts/stack_lease.sh)$' || true)"
  [ -z "$left" ] || { echo "LEFT IN THE COPY after $1:"; echo "$left"; ok=0; }
}
verdict() { # name, want, log, for red: the pattern every named case's failure must show
  if [ "$2" = green ]; then
    if grep -qE "^FAILED|[0-9]+ failed|error" "$3"; then echo "WRONG (something failed): $1"; grep -E "^FAILED" "$3"; ok=0; else echo "AS IT MUST BE (green): $1: $(grep -E '[0-9]+ passed' "$3" | tail -1)"; fi
  else
    if grep -qE "$4" "$3"; then echo "AS IT MUST BE (red): $1"; grep -E "^FAILED" "$3" | sed 's/ - .*//'; else echo "WRONG (not red as it must be): $1"; tail -3 "$3"; ok=0; fi
  fi
}
L=$(mktemp)
echo "head $(git rev-parse --short HEAD) of the copy, on $(hostname), processes $(ls -d /proc/[0-9]* | wc -l)"
git apply $D/stack_lease_sh.diff || { echo "the script diff does not apply"; exit 1; }
FOUR='start_line or two_runs_named_alike or two_runs_of_one_lane'

# 1. The coupling, planted where it lives: each run's process table a busy host's (8,000 processes, none of the
#    run's), not an empty one of its own. The four that wait on a run's exit go red waiting.
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
verdict "plant: every run's table a busy host's" red $L "4 failed"
git checkout -q HEAD -- $T
stray "the busy table"

# 2. Each reaping test given the empty table instead of /proc: red, so the default hides no reaping.
for name in test_a_run_reaps_a_server_that_left_its_process_group test_the_reaper_leaves_every_process_outside_the_run_alone test_a_runs_log_holds_no_error_of_the_reapers_own_reading; do
  python3 - "$T" "$name" <<'PY'
import sys,re; p,name=sys.argv[1],sys.argv[2]; s=open(p).read()
i=s.index(f"def {name}("); j=s.index("\ndef ", i+1)
body=s[i:j]; assert body.count(", proc=REAL_PROC")>=1, name
s=s[:i]+body.replace(", proc=REAL_PROC","")+s[j:]; open(p,"w").write(s)
PY
  py -k "$name" > $L
  verdict "plant: $name on the empty table" red $L "1 failed"
  git checkout -q HEAD -- $T
  stray "$name on the empty table"
done

# 3. The reaper reading /proc whatever it is given: its scan and its re-read (main's script), then the re-read alone.
git checkout -q HEAD -- scripts/stack_lease.sh
py -k test_the_reaper_reads_the_process_table_it_is_given > $L
verdict "plant: main's script (the table not read)" red $L "1 failed"
git apply $D/stack_lease_sh.diff
python3 - scripts/stack_lease.sh <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
a='"${OSPREY_PROC_ROOT:-/proc}/$1/environ"'; assert s.count(a)==1
s=s.replace(a,'"/proc/$1/environ"'); open(p,"w").write(s)
PY
py -k test_the_reaper_reads_the_process_table_it_is_given > $L
verdict "plant: the re-read before each signal reads /proc" red $L "1 failed"
git checkout -q HEAD -- scripts/stack_lease.sh
git apply $D/stack_lease_sh.diff

# 4. Unplanted, with the host as busy as a night of lane runs: 2,000 more processes and half the cores taken.
pids=(); for i in $(seq 1 2000); do sleep 900 & pids+=($!); done
for i in $(seq 1 $(( $(nproc) / 2 ))); do ( while :; do :; done ) & pids+=($!); done
echo "busy: processes $(ls -d /proc/[0-9]* | wc -l), burners $(( $(nproc) / 2 )) of $(nproc) cores"
py --durations=6 > $L
kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null
verdict "unplanted, the host busy: the whole file" green $L
stray "the unplanted run"
grep -E "s call .*(start_line|two_runs)" $L
git checkout -q HEAD -- scripts/stack_lease.sh
rm -f $L
git status --short
[ $ok = 1 ] && echo "every plant red, unplanted green" || { echo "A PLANT WENT THE WRONG WAY"; exit 1; }
