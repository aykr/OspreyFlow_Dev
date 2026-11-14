"""rules-b route-collapse: each plant breaks one branch of the collapse in scripts/lanes_heartbeat.sh, in the shape
the code has, and names the test that must go red for it (rule 15). The script is restored from the text saved
before the first plant, never from git, and checked byte for byte at the end.

Run from OspreyFlow_Core: ../OspreyFlow_Build/.venv-free; uses .venv/bin/pytest with the offline ports pinned.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "lanes_heartbeat.sh"
TESTS = "../OspreyFlow_Build/tests/test_lanes_heartbeat_route.py"
NEW = ("sub_step or fixes or whole_steps or steps_line or whole_number or long_list or steps_keeps or "
       "full_is or steps_done_line")

PLANTS = [
    ("a running step folds into its group",
     'if ($route[$i][8] ne "done") { push @kept',
     'if ($route[$i][8] !~ /^(done|running)$/) { push @kept',
     "test_one_sub_step_not_done_stays_expanded_and_the_rest_collapse"),
    ("a number's group shows its span with nothing listed when partly done",
     "if (@d == @m) { push @kept", "if (1) { push @kept",
     "test_one_sub_step_not_done_stays_expanded_and_the_rest_collapse"),
    ("the route's # steps line is not read",
     '$as_step{$_} = 1 for /^# steps', '$as_step{$_} = 1 for /^# nothing',
     "test_the_done_fixes_and_the_done_whole_steps_are_one_line_each_with_their_ids"),
    ("a long id list cut, not wrapped",
     'if (length("$line $_") > 120) { push @kept, [$line, []]; $line = "     " } $line .= " $_"',
     '$line .= " $_"; $line = cut($line, 120)',
     "test_a_long_list_of_done_ids_wraps_and_drops_none"),
    ("--steps not passed to the view",
     'P_STEPS="${P_STEPS:-}" perl', 'P_STEPS="" perl',
     "test_steps_keeps_one_line_a_step"),
    ("a whole number with sub-steps left among the steps",
     'return "n$1" if $id =~ /^(\\d+)/ && $sub{$1};', 'return "n$1" if $id =~ /^(\\d+)\\D/ && $sub{$1};',
     "test_a_whole_number_with_sub_steps_is_in_their_line"),
]


def run(k: str) -> str:
    env = {k2: v for k2, v in os.environ.items() if k2 != "OSPREY_LANE"}
    env.update(ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway",
               VALKEY_PORT="59993", CLICKHOUSE_HTTP_PORT="59994", PYTHONPYCACHEPREFIX=tempfile.mkdtemp())
    out = subprocess.run([".venv/bin/pytest", "-p", "no:cacheprovider", "-c", "../OspreyFlow_Build/pytest.ini",
                          "-q", "-rA", TESTS, "-k", k], capture_output=True, text=True, env=env)
    return out.stdout


def main() -> int:
    saved = SCRIPT.read_bytes()
    bad = 0
    try:
        for name, old, new, must in PLANTS:
            text = saved.decode("utf-8")
            assert text.count(old) == 1, (name, text.count(old))
            SCRIPT.write_bytes(text.replace(old, new).encode("utf-8"))
            out = run(NEW)
            red = [line.split("::")[-1].split()[0] for line in out.splitlines() if line.startswith("FAILED")]
            ok = must in red
            bad += not ok
            print(f"{'RED ' if ok else 'GREEN?'} {name}: {must} {'failed' if ok else 'did not fail'}; red: {red}")
            for line in out.splitlines():
                if line.startswith("E ") and must.split("test_")[-1][:20]:
                    print("    " + line[:200])
                    break
    finally:
        SCRIPT.write_bytes(saved)
    assert SCRIPT.read_bytes() == saved
    control = run(NEW).splitlines()[-1]
    print(f"control (restored): {control}")
    return 1 if bad or "failed" in control else 0


if __name__ == "__main__":
    sys.exit(main())
