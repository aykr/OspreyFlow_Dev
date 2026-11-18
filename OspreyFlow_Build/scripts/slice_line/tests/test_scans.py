"""A slice's checks include every pure test that scans the files it touches (the owner's order of 18 November 2026,
after AD2): scan_map.tsv, the line's, maps each whole-tree scanner to the prefixes it walks, and the Stop hook runs
the ones a slice's branch reaches. The map is shown complete: a pure test that walks a folder with no row fails.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from test_gates import SRC, sh, started, stop_gate, world  # noqa: F401  (world is a fixture)

sys.path.insert(0, str(SRC))
import scan_select  # noqa: E402

SCANNER = '''from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_section_imports_the_forbidden_module():
    bad = [p.name for p in (ROOT / "OspreyFlow_Core/apps").rglob("*.ts") if "import forbidden" in p.read_text()]
    assert bad == [], bad
'''


def scanning(w):
    """A repository with one whole-tree scanner, mapped; S1 started, its worktree with an environment."""
    r = w["repo"]
    (r / "OspreyFlow_Build/pytest.ini").write_text("[pytest]\n")
    (r / "OspreyFlow_Build/tests").mkdir(parents=True, exist_ok=True)
    (r / "OspreyFlow_Build/tests/test_scan_demo.py").write_text(SCANNER)
    (r / "OspreyFlow_Core/apps").mkdir(parents=True, exist_ok=True)
    (r / "OspreyFlow_Core/apps/section.ts").write_text("export const x = 1;\n")
    (r / ".gitignore").write_text("Claude outputs/\n.venv/\n")
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'test: a scanner'", r, w["env"])
    (w["data"] / "bin/scan_map.tsv").write_text(
        "# test\tprefixes\twhy\ntests/test_scan_demo.py\tOspreyFlow_Core/apps/\twalks the apps' sources\n")
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    venv = wt / "OspreyFlow_Core/.venv/bin"
    venv.mkdir(parents=True)
    (venv / "python").write_text(f'#!/bin/sh\nexec "{w["py"]}" "$@"\n')
    (venv / "python").chmod(0o755)
    (wt / "accept.sh").write_text("exit 0\n")
    sh("git add accept.sh && git commit -qm 'test: S1'", wt, w["env"])
    return wt


def test_the_stop_hook_runs_the_scan_mapped_to_a_touched_path_and_goes_red(world):
    w = world
    wt = scanning(w)
    (wt / "OspreyFlow_Core/apps/section.ts").write_text("import forbidden from './x';\nexport const x = 1;\n")
    sh("git commit -qam 'feat: a section imports more'", wt, w["env"])
    out = stop_gate(w, wt)  # the slice's own checks (`true`) and acceptance are green
    assert out and out["decision"] == "block", out
    assert "test_scan_demo.py" in out["reason"] and "test_no_section_imports_the_forbidden_module" in out["reason"]
    assert "section.ts" in out["reason"] and "No module named" not in out["reason"], out["reason"]


def test_the_stop_hook_runs_no_scan_for_a_path_no_row_names_and_records_those_it_ran(world):
    w = world
    wt = scanning(w)
    (wt / "README.md").write_text("only words\n")
    sh("git commit -qam 'docs: words'", wt, w["env"])
    assert stop_gate(w, wt) is None
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    rec = json.loads((w["data"] / f"records/S1/tests-{tip}.json").read_text())
    assert [r["name"] for r in rec["results"]] == ["checks", "acceptance"], rec
    (wt / "OspreyFlow_Core/apps/other.ts").write_text("export const y = 2;\n")
    sh("git add -A OspreyFlow_Core/apps && git commit -qm 'feat: another section'", wt, w["env"])
    assert stop_gate(w, wt) is None
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    rec = json.loads((w["data"] / f"records/S1/tests-{tip}.json").read_text())
    scans = [r for r in rec["results"] if r["name"] == "scans"]
    assert scans and scans[0]["tests"] == ["tests/test_scan_demo.py"] and scans[0]["exit"] == 0, rec


def test_the_stop_hook_refuses_when_the_scan_map_cannot_be_read(world):
    w = world
    wt = scanning(w)
    (w["data"] / "bin/scan_map.tsv").unlink()
    out = stop_gate(w, wt)
    assert out and out["decision"] == "block" and "scan map" in out["reason"], out


# ------------------------------------------------------------------ the map is complete


def synthetic(tmp: Path, extra: dict) -> Path:
    b = tmp / "OspreyFlow_Build"
    files = {"Makefile": "test:\n\tpytest --ignore=../OspreyFlow_Build/tests/live ../OspreyFlow_Build/tests\n",
             "tests/test_plain.py": "def test_x():\n    assert 1\n",
             "tests/live/test_live_walker.py": "from pathlib import Path\nlist(Path('.').rglob('*'))\n",
             "tools/__init__.py": "", **extra}
    for rel, text in files.items():
        (b / rel).parent.mkdir(parents=True, exist_ok=True)
        (b / rel).write_text(text)
    return b


def test_the_scan_map_check_finds_a_pure_test_that_walks_with_no_row(tmp_path):
    b = synthetic(tmp_path, {
        "tests/test_walker.py": "from pathlib import Path\nROOT = Path(__file__).parents[2]\n"
                                "def test_w():\n    list((ROOT / 'OspreyFlow_Core').rglob('*.py'))\n",
        "tests/test_via_tool.py": "from tools.walker import scan\n\ndef test_v():\n    scan()\n",
        "tests/test_via_run.py": "import subprocess\nsubprocess.run(['python', '-m', 'tools.walker'])\n",
        "tools/walker.py": "import os\n\ndef scan():\n    return list(os.walk('.'))\n",
    })
    assert scan_select.unmapped(b, []) == ["tests/test_via_run.py", "tests/test_via_tool.py", "tests/test_walker.py"]
    table = scan_select.load("tests/test_walker.py\tOspreyFlow_Core/\tx\ntests/test_via_tool.py\t-\ty\n"
                             "tests/test_via_run.py\t-\tz\n")
    assert scan_select.unmapped(b, table) == []


def test_the_real_scan_map_names_every_pure_walker_and_nothing_stale():
    build = SRC.parents[1]
    table = scan_select.entries(SRC / "scan_map.tsv")
    assert scan_select.unmapped(build, table) == []
    assert scan_select.stale(build, table) == []


def test_the_real_scan_map_selects_test_admin_sections_for_a_change_to_a_section():
    table = scan_select.entries(SRC / "scan_map.tsv")
    got = scan_select.select(["OspreyFlow_Core/apps/workspace/src/admin/sections/People.tsx"], table)
    assert "tests/services/api/test_admin_sections.py" in got, got


def test_the_scan_map_check_finds_a_stale_row(tmp_path):
    b = synthetic(tmp_path, {})
    (tmp_path / "OspreyFlow_Core/apps").mkdir(parents=True)
    table = scan_select.load("tests/test_plain.py\tOspreyFlow_Core/apps/,OspreyFlow_Core/apsp/\ttypo\n"
                             "tests/test_gone.py\t-\tremoved\n")
    assert scan_select.stale(b, table) == ["tests/test_gone.py: no such test",
                                           "tests/test_plain.py: OspreyFlow_Core/apsp/ names nothing"]
