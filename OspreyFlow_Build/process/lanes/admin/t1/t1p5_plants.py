# ruff: noqa: E501 - the plants are the script's own lines, verbatim
"""T1 part 5's planted faults (CLAUDE.md rule 15). Each plant edits `OspreyFlow_Build/scripts/stack_lease.sh` at the
line the behaviour lives on, runs the cases meant to catch it, expects them red, and restores the file. The script and
its tests are the orchestrator's files, sent as `stack-lease-T1p5.diff`: the harness applies it first and reverses it
at the end, so each fault is planted where it will merge. The control is the whole of `tests/test_stack_lease.py`,
green before and after. The reaper's cases need /proc and setsid, so this runs on a Linux host, from `OspreyFlow_Core`:

    stack_lease.sh offline admin -- .venv/bin/python ../OspreyFlow_Build/process/lanes/admin/t1/t1p5_plants.py

A case is red only on exit 1 with "failed" and no "error" in its summary; a case that only skips is MISSED (the plant
proved nothing), anything else a harness fault. The server's copy is no git checkout, so the diff is applied with
`t1/apply_diff.py`, which refuses (writing nothing) unless every hunk's old lines are there exactly once: a script that
already holds the change, or any other, stops the run before a plant. Every file is restored in a `finally`. Nothing
here touches docker: every case runs the script against the suite's fake docker and ssh. (`reset` is its own step
now, the orchestrator's split ruling: its plants went with it.)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CORE = Path.cwd()
ROOT = CORE.parent
TARGET = CORE / "../OspreyFlow_Build/scripts/stack_lease.sh"
DIFF = ROOT / "OspreyFlow_Build/process/lanes/admin/stack-lease-T1p5.diff"
TESTS = "../OspreyFlow_Build/tests/test_stack_lease.py"
UP = "test_a_run_on_a_stack_not_wholly_up_is_refused_before_anything_is_sent"

# (name, [(old text, new text), ...], test ids that must go red)
PLANTS: list[tuple[str, list[tuple[str, str]], list[str]]] = [
    (
        "remote runs without checking the stack is up",
        [
            (
                '    [ -n "$h" ] || { echo "Stack $s runs on this machine: run the command here, not with remote." >&2; exit 1; }\n'  # noqa: E501
                '    stack_wholly_up "$s" || exit 1\n',
                '    [ -n "$h" ] || { echo "Stack $s runs on this machine: run the command here, not with remote." >&2; exit 1; }\n',  # noqa: E501
            )
        ],
        [
            f"{UP}[remote-one-down]",
            f"{UP}[remote-all-down]",
            "test_a_run_is_refused_when_docker_cannot_say_whether_the_stack_is_up",
        ],
    ),
    (
        "live runs without checking the stack is up",
        [
            (
                '    [ -n "$h" ] || { echo "Stack $s runs on this machine: run the selection here, not with live." >&2; exit 1; }\n'  # noqa: E501
                '    stack_wholly_up "$s" || exit 1\n',
                '    [ -n "$h" ] || { echo "Stack $s runs on this machine: run the selection here, not with live." >&2; exit 1; }\n',  # noqa: E501
            )
        ],
        [f"{UP}[live-one-down]", f"{UP}[live-all-down]"],
    ),
    (
        "one container up taken for the stack up (the old stack_state's test)",
        [('  [ -z "$missing" ] && return 0\n', '  [ -n "$running" ] && return 0\n')],
        [f"{UP}[remote-one-down]", f"{UP}[live-one-down]"],
    ),
    (
        "docker's failure read as the stack up",
        [
            (
                '  if ! running="$(docker_for "$s" ps --format \'{{.Names}}\' $filters 2>&1)"; then\n',
                '  if ! running="$(docker_for "$s" ps --format \'{{.Names}}\' $filters 2>&1)"; then return 0\n',
            )
        ],
        ["test_a_run_is_refused_when_docker_cannot_say_whether_the_stack_is_up"],
    ),
    (
        "the check asked of this machine, not the stack's host",
        [
            (
                '  if ! running="$(docker_for "$s" ps --format \'{{.Names}}\' $filters 2>&1)"; then\n',
                "  if ! running=\"$(docker ps --format '{{.Names}}' $filters 2>&1)\"; then\n",
            )
        ],
        ["test_a_run_on_a_wholly_up_stack_asks_only_its_own_containers_on_its_own_host"],
    ),
    (
        "the run is not tagged",
        [("    printf 'export OSPREY_RUN_TAG=$HOME/%s\\n' \"$run\"\n", "")],
        [
            "test_a_run_reaps_a_server_that_left_its_process_group",
            "test_a_run_ended_by_a_signal_still_reaps_its_server",
            "test_remote_runs_the_command_on_the_stack_s_host_with_its_ports_and_lease",
        ],
    ),
    (
        "the reaper is not run when the run ends",
        [("    printf 'trap osprey_reap EXIT\\n'\n", "")],
        [
            "test_a_run_reaps_a_server_that_left_its_process_group",
            "test_a_run_ended_by_a_signal_still_reaps_its_server",
        ],
    ),
    (
        "the tag matched as a prefix, so another run's processes are ended",
        [('grep -qxF "OSPREY_RUN_TAG=$tag"', 'grep -qF "OSPREY_RUN_TAG=$tag"')],
        ["test_reap_ends_what_a_run_whose_wrapper_was_killed_left_behind"],
    ),
    (
        # Planted as "any run under the same home", never "any tag at all": a wider plant could end another
        # session's processes on this shared host.
        "every run's processes under the same home ended, not this run's alone",
        [
            (
                'grep -qxF "OSPREY_RUN_TAG=$tag"; }',
                'grep -qF "OSPREY_RUN_TAG=${tag%%/osprey-runs/*}/osprey-runs/"; }',
            )
        ],
        ["test_the_reaper_leaves_every_process_outside_the_run_alone"],
    ),
    (
        "reap reaps nothing",
        [('osprey_reap "$t" || exit $?; echo', "echo")],
        ["test_reap_ends_what_a_run_whose_wrapper_was_killed_left_behind"],
    ),
    (
        "must-fix 4: reap ends a run that is still running",
        [
            (
                'if [ -f "$t/pid" ] && kill -0 "$(cat "$t/pid")" 2>/dev/null; then echo "The run $t is still running: stop it, or let it end; nothing reaped." >&2; exit 3; fi; ',
                "",
            )
        ],
        ["test_reap_refuses_a_run_that_is_still_running"],
    ),
    (
        "must-fix 4: an empty tag reaps every process tagged with nothing",
        [
            (
                '  [ -n "$tag" ] || { echo "No run tag to reap by: nothing reaped." >&2; return 2; }\n',
                "",
            )
        ],
        ["test_the_reaper_refuses_an_empty_tag"],
    ),
    (
        "must-fix 5: no KILL pass (TERM alone)",
        [
            (
                '  if [ -n "$hit" ]; then sleep 2; for pid in $hit; do if osprey_tagged "$pid"; then kill -9 "$pid" 2>/dev/null; fi; done; fi\n',
                "",
            )
        ],
        ["test_the_reaper_kills_what_survives_term"],
    ),
    (
        "must-fix 5: the KILL pass sent to each pid without reading it again",
        [
            (
                'do if osprey_tagged "$pid"; then kill -9 "$pid" 2>/dev/null; fi; done; fi',
                'do kill -9 "$pid" 2>/dev/null; done; fi',
            )
        ],
        ["test_the_kill_pass_reads_each_pid_again_and_spares_one_now_another_process"],
    ),
    (
        "must-fix 6: the run's folder named by the second alone",
        [
            ("-$(od -An -N4 -tx4 /dev/urandom | tr -d ' ')\"", '"'),
            ("mkdir -p $rmeta/runs && mkdir $run && cat", "mkdir -p $run && cat"),
        ],
        ["test_two_runs_of_one_lane_in_one_second_never_share_a_folder"],
    ),
    (
        "the start call's backgrounded list holding ssh's output open",
        [("> $run/log 2>&1 < /dev/null; } > /dev/null 2>&1 &", "> $run/log 2>&1 < /dev/null; } &")],
        ["test_the_start_call_returns_while_the_run_goes_on"],
    ),
]


APPLY = ROOT / "OspreyFlow_Build/process/lanes/admin/t1/apply_diff.py"


def apply(*flags: str) -> bool:
    done = subprocess.run(
        [sys.executable, str(APPLY), *flags, str(DIFF)], capture_output=True, text=True, check=False
    )
    print(done.stdout.strip() or done.stderr.strip())
    return done.returncode == 0


def run(nodeids: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p", "no:cacheprovider", *nodeids],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return proc.returncode, lines[-1] if lines else proc.stderr[-300:]


def verdict(rc: int, tail: str) -> str:
    if rc == 1 and "failed" in tail and "error" not in tail:
        return "red"
    if rc == 0:
        return "MISSED" + (
            " (skipped: proves nothing here)" if "skipped" in tail and "passed" not in tail else ""
        )
    return "HARNESS FAULT"


def main() -> int:
    if not apply():
        print(
            "refused: stack-lease-T1p5.diff does not apply to this copy (already applied, or moved)"
        )
        return 2
    reds = missed = faults = runs = 0
    try:
        original = TARGET.read_text()
        rc, tail = run([TESTS])
        print(
            f"control (the diff applied, no plant): {'green' if rc == 0 else 'RED'} (exit {rc}) — {tail}"
        )
        if rc != 0:
            return 1
        for name, edits, ids in PLANTS:
            planted = original
            for old, new in edits:
                if planted.count(old) != 1:
                    print(
                        f"HARNESS FAULT, plant misses its site ({planted.count(old)} matches): {name}"
                    )
                    faults += 1
                    break
                planted = planted.replace(old, new)
            else:
                TARGET.write_text(planted)
                try:
                    for test_id in ids:
                        rc, tail = run([f"{TESTS}::{test_id}"])
                        result = verdict(rc, tail)
                        runs += 1
                        reds += result == "red"
                        missed += result.startswith("MISSED")
                        faults += result == "HARNESS FAULT"
                        print(f"[{name}] {test_id}: {result} (exit {rc}) — {tail}")
                finally:
                    TARGET.write_text(original)
    finally:
        apply("--reverse")
    rc, tail = run([TESTS])
    print(
        f"control (restored, main's script): {'green' if rc == 0 else 'RED'} (exit {rc}) — {tail}"
    )
    print(
        f"{len(PLANTS)} plants, {runs} case runs: {reds} red, {missed} missed, {faults} harness faults"
    )
    return 1 if missed or faults or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
