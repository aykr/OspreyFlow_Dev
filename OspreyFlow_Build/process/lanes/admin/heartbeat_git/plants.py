"""The heartbeat's done-from-git and ready plants (the owner's order, 14 November 2026; rule 15). Each is planted
alone in scripts/lanes_heartbeat.sh, the one test it names run, and the script restored from git. A plant counts
as red only when every failing case stopped at the assertion it names (the line pytest's --tb=line reports).

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/heartbeat_git/plants.py
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPT = "OspreyFlow_Build/scripts/lanes_heartbeat.sh"
TEST = "tests/test_lanes_heartbeat_route.py"

PLANTS = [
    ("no view reads git: the typed rows stand",
     'case "${1:-}" in "" | --overview | --full | --lanes | show | summary) read_git ;; esac\n', "",
     "typed_building_whose_branch", r'assert " done" in _row\(out, "3c"\)'),
    ("the route alone reads git (the first version's shape)",
     '"" | --overview | --full | --lanes | show | summary) read_git', '"") read_git',
     "every_view_reads", r'assert "OVERALL: 5 of 11 steps done"'),
    ("a merged head counted whatever its merge's subject names (a branch cut afresh at a lane's merged head)",
     "grep { names_branch($_, $branch) }", "grep { 1 }",
     "not_on_main_by_a_merge", r'lane/rules-next'),
    ("the merger brief's own subject form not read",
     r" || $subject =~ m{^merge\(lane/([^)\s]+)\): ([^,\s]+)})", ")",
     "merger_brief_s_form", r'assert " done" in _row\(gitroute\(16, _branch\(PROGRESS, "v052-fixes", "lane/case-cluster"\)\), "3e"\)'),
    ("a branch guessed from the lane and step's names where the row names none",
     'my $branch = @f >= 6 ? $f[5] =~ s/^\s+|\s+$//gr : "";', 'my $branch = @f >= 6 ? $f[5] =~ s/^\s+|\s+$//gr : "lane/$f[0]-$f[1]";',
     "never_given_one_by_its_name", r'assert " running" in _row\(gitroute\(16\), "3c"\)'),
    ("a LANDED line counted without `done` (a part's merge, named by its step)",
     ' && $f[4] eq "done" }', ' }',
     "landed_line_counts_only", r'assert " running" in _row\(out, "3c"\) and " not started" in _row\(out, "B"\)'),
    ("a LANDED line split on spaces alone (a step with a space never read)",
     'my @f = /\t/ ? split(/\t/) : split(/ +/);', 'my @f = split(/\s+/);',
     "landed_line_counts_only", r'"platform: P5b rows" not in'),
    ("an empty middle field collapsed (the branch read from the wrong column)",
     'my @f = split /\t/, $line, -1;', 'my @f = split /\t+/, $line;',
     "any_row_shape", r'assert "docs" not in'),
    ("a missing repository ends the view",
     "refs/heads 2>/dev/null || true)\"", "refs/heads)\"",
     "with_no_repository", r'assert out\.returncode == 0'),
    ("no step shown ready",
     '  next unless $r->[8] eq "not started"', '  next; next unless $r->[8] eq "not started"',
     "after_steps_are_all_done_shows_ready", r'assert " ready, 2 days ahead'),
    ("ready without the days it could gain",
     '$r->[8] = $gain > 0 ?', '$r->[8] = 0 ?',
     "after_steps_are_all_done_shows_ready", r'assert " ready, 2 days ahead'),
    ("ready when any `after` step is done, not every one",
     'next if !@after || grep { ($state_of{$_} // "") ne "done" } @after;',
     'next if !@after || !grep { ($state_of{$_} // "") eq "done" } @after;',
     "after_steps_are_all_done_shows_ready", r'assert " not started" in _row\(out, "4"\)'),
    ("an `after` naming no route step taken as done",
     '($state_of{$_} // "") ne "done"', '($state_of{$_} // "done") ne "done"',
     "ready_needs_every_after_step", r'assert "ready" not in _row\(gitroute\(14, progress\), "3d"\)'),
    ("a step under way shown ready",
     '  next unless $r->[8] eq "not started"', '  next unless $r->[8] ne "done"',
     "ready_needs_every_after_step", r'assert " running" in _row\(gitroute\(14, progress\), "B"\)'),
    ("an `after` list split on commas alone",
     r'split /[\s,]+/, $r->[6];', r'split /\s*,\s*/, $r->[6];',
     "after_list_with_spaces", r'assert " ready" in _row'),
]


def main() -> int:
    if subprocess.run(["git", "diff", "--quiet", "--", SCRIPT], cwd=ROOT).returncode:
        sys.exit(f"{SCRIPT} has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# heartbeat plants at {head}")
    env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | {
        "PYTHONPYCACHEPREFIX": tempfile.mkdtemp(), "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992",
        "POSTGRES_PASSWORD": "throwaway", "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
    source = (ROOT / "OspreyFlow_Build" / TEST).read_text(encoding="utf-8").splitlines()
    missed = 0
    for name, old, new, k, why in PLANTS:
        path = ROOT / SCRIPT
        s = path.read_text(encoding="utf-8")
        assert s.count(old) == 1, f"{name}: the site is not there exactly once"
        path.write_text(s.replace(old, new), encoding="utf-8")
        try:
            out = subprocess.run(
                ["../OspreyFlow_Core/.venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST,
                 "-k", k, "--tb=line"],
                cwd=ROOT / "OspreyFlow_Build", capture_output=True, text=True, env=env,
            ).stdout
        finally:
            subprocess.run(["git", "checkout", "--", SCRIPT], cwd=ROOT, check=True)
        stops = [int(n) for n in re.findall(rf"{re.escape(TEST)}:(\d+): ", out)]
        failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
        if not failed and not re.search(r"\d+ passed", out):
            sys.exit(f"{name}: the test did not run:\n{out[-2000:]}")
        off = [source[n - 1].strip() for n in stops if not re.search(why, source[n - 1].strip())]
        red = failed > 0 and len(stops) == failed and not off
        missed += not red
        said = "RED at its assertion" if red else ("GREEN" if not failed else f"red for another reason: {off or stops}")
        print(f"== {name} (must fail at /{why}/): {said}, {failed} failed")
        for n in stops:
            print(f"   stopped at {TEST}:{n}: {source[n - 1].strip()[:150]}")
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
