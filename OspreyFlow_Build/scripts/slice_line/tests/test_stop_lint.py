"""Lint and the scan-map check in the builder's Stop check (LINE_FIXES_5_BRIEF.md, 4).

Builders handed back with ruff, eslint or the scan-map check red, and the conductor found it at the pre-merge check
(SE7, PL4c and PL4d2 each lost a round or a merge attempt to it). The Stop hook now runs, on the files the branch
changed against its base: `ruff check` and `ruff format --check` on OspreyFlow_Core's Python (the real ruff, beside the
python running this suite), eslint on its JavaScript and TypeScript (a stand-in answering as eslint answers: its
stylish report and exit 1), and the scan-map check on every new test under OspreyFlow_Build/tests. Red is red: the stop
is blocked with the finding, and the builder goes on in the same round. A tool that is not there is red too, with the
command that installs it in the worktree.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from test_gates import sh, started, stop_gate, world  # noqa: F401  (world is a fixture)

RUFF = Path(sys.executable).parent / "ruff"
#: eslint's stylish report for `no-var`, and its exit 1, for any file holding a `var`.
ESLINT = r'''#!/bin/sh
bad=0
for f in "$@"; do
  case "$f" in -*) continue;; esac
  if grep -n 'var ' "$f" >/dev/null 2>&1; then
    printf '\n%s\n  1:1  error  Unexpected var, use let or const instead  no-var\n' "$PWD/$f"; bad=1
  fi
done
[ $bad = 1 ] && printf '\n✖ 1 problem (1 error, 0 warnings)\n'
exit $bad
'''
CLEAN_PY = 'def answer() -> int:\n    return 42\n'
WALKER = ('from pathlib import Path\n\n\ndef test_every_page_is_there():\n'
          '    assert list(Path(__file__).parent.rglob("*.md")) is not None\n')
PURE = 'def test_one():\n    assert 1 == 1\n'


def tools(w, ruff=True, eslint=True):
    b = w["tmp"] / "lintbin"
    b.mkdir(exist_ok=True)
    for name in ("ruff", "eslint"):
        (b / name).unlink(missing_ok=True)
    if ruff:
        (b / "ruff").symlink_to(RUFF)
    if eslint:
        (b / "eslint").write_text(ESLINT)
        (b / "eslint").chmod(0o755)
    w["env"]["PATH"] = f"{b}{os.pathsep}/usr/bin{os.pathsep}/bin"
    # the installed scan map, as the line's tests need it here: one row for the pure walker the suite knows
    (w["data"] / "bin/scan_map.tsv").write_text("# test\tprefixes\twhy\n")


def branch(w, files: dict):
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    (wt / "accept.sh").write_text("exit 0\n")
    for rel, text in files.items():
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text)
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'feat: S1'", wt, w["env"])
    return wt


def record(w, wt):
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    f = w["data"] / f"records/S1/tests-{tip}.json"
    return json.loads(f.read_text()) if f.exists() else None


def state(w):
    return json.loads((w["data"] / "records/S1/state.json").read_text())


def test_a_changed_python_file_with_a_lint_error_is_red_in_the_same_round(world):
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Core/pkg/mod.py": "import os\n\n\n" + CLEAN_PY})
    round0 = state(w)["round"]
    out = stop_gate(w, wt)
    assert out and out["decision"] == "block", out
    assert "RED: ruff check" in out["reason"] and "F401" in out["reason"] and "pkg/mod.py" in out["reason"], out
    assert "attempt 1 of 6" in out["reason"] and state(w)["round"] == round0 and record(w, wt) is None


def test_a_changed_python_file_not_formatted_is_red(world):
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Core/pkg/mod.py": "def answer() -> int:\n    return   42\n"})
    out = stop_gate(w, wt)
    assert out and "RED: ruff format" in out["reason"] and "pkg/mod.py" in out["reason"], out


def test_a_changed_typescript_file_with_an_eslint_error_is_red(world):
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Core/apps/x/src/a.ts": "var a = 1;\nexport { a };\n"})
    out = stop_gate(w, wt)
    assert out and "RED: eslint" in out["reason"] and "no-var" in out["reason"] and "a.ts" in out["reason"], out


def test_a_new_test_that_walks_a_folder_with_no_scan_map_row_is_red(world):
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Build/tests/test_walker.py": WALKER})
    out = stop_gate(w, wt)
    assert out and "RED: scan map" in out["reason"] and "tests/test_walker.py" in out["reason"], out


def test_its_row_waiting_on_main_makes_it_green(world):
    w = world
    tools(w)
    rows = w["repo"] / "OspreyFlow_Build/process/lanes/v062/scan_rows/S1.tsv"
    rows.parent.mkdir(parents=True)
    rows.write_text("tests/test_walker.py\t-\twalks its own folder of pages only\n")
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: S1 scan row' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    wt = branch(w, {"OspreyFlow_Build/tests/test_walker.py": WALKER})
    assert stop_gate(w, wt) is None and record(w, wt)["green"]


def test_lint_and_scan_map_red_together_are_both_named(world):
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Core/pkg/mod.py": "import os\n", "OspreyFlow_Build/tests/test_walker.py": WALKER})
    out = stop_gate(w, wt)
    assert out and "RED: ruff check" in out["reason"] and "RED: scan map" in out["reason"], out


def test_a_clean_branch_is_green_and_its_record_names_the_lint(world):
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Core/pkg/mod.py": CLEAN_PY, "OspreyFlow_Core/apps/x/src/a.ts": "export const a = 1;\n",
                    "OspreyFlow_Build/tests/test_pure.py": PURE})
    assert stop_gate(w, wt) is None
    names = [r["name"] for r in record(w, wt)["results"]]
    assert {"ruff check", "ruff format", "eslint", "scan map"} <= set(names), names


def test_a_lint_tool_that_is_not_there_is_red_with_how_to_install_it(world):
    w = world
    tools(w, ruff=False)
    wt = branch(w, {"OspreyFlow_Core/pkg/mod.py": CLEAN_PY})
    out = stop_gate(w, wt)
    assert out and "RED: ruff check" in out["reason"] and "uv sync --frozen" in out["reason"], out


def test_files_outside_cis_lint_are_not_linted(world):
    """CI lints OspreyFlow_Core's Python only: a script in OspreyFlow_Build with Core's complaints is not red here."""
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Build/scripts/x.py": "import os\n"})
    assert stop_gate(w, wt) is None
