"""The merge gate's pytest runs use a temp base of their own (LINE_FIXES_3_BRIEF.md, 1e).

pytest keeps only the newest few `pytest-N` folders per user under one base and removes the older ones when a run
starts; SE3's second merge attempt and GG1's first (19 November 2026) failed at test_stack_lease.py when a folder of
theirs was gone. The real pytest runs here, under the environment merge_slice.slice_env builds (the slice's commands,
on the merge result) and merge_slice.ci_env builds (the full gate), with the caller's TMPDIR as the shared base every
other pytest on the Mac uses.
"""
from __future__ import annotations

import json
import os
import re

from test_gates import built, fake, gate, merge, run_gate, sh, verified, world  # noqa: F401  (fixtures)

TMP_TEST = '''import os


def test_leaves_a_marker(tmp_path):
    (tmp_path / "marker").write_text(os.environ.get("WHO", "?"))
'''


def test_pytest_base_a_merges_runs_are_not_removed_by_other_pytest_runs_on_the_mac(world):
    w = world
    shared = w["tmp"] / "shared-tmp"
    shared.mkdir()
    tree = w["tmp"] / "merge-tree"
    tree.mkdir()
    (tree / "test_one.py").write_text(TMP_TEST)
    code = f"""
import json, os, subprocess, sys
from pathlib import Path
sys.path.insert(0, {str(w['lines'])!r})
import merge_slice as m
tree = Path({str(tree)!r})
env = m.slice_env(tree, Path({str(w['tmp'] / 'merge.log')!r}), None, None, pytest_base=Path({str(w['tmp'] / 'envs' / 'pytest-after')!r}))
def pytest(env, who):
    subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_one.py"], cwd=tree,
                   env={{**env, "WHO": who}}, check=True, capture_output=True)
pytest(env, "merge")
for i in range(5):  # another pytest on the Mac (a builder's checks, a verifier), on the shared base
    other = {{k: v for k, v in os.environ.items() if k != "PYTEST_DEBUG_TEMPROOT"}}
    pytest(other, f"other-{{i}}")
print(json.dumps({{"base": env.get("PYTEST_DEBUG_TEMPROOT", ""),
                   "markers": sorted(str(p) for p in Path({str(w['tmp'])!r}).rglob("marker"))}}))
"""
    p = sh([w["py"], "-c", code], w["repo"], {**w["env"], "TMPDIR": str(shared)}, check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out["base"] == str(w["tmp"] / "envs" / "pytest-after"), out
    mine = [m for m in out["markers"] if m.startswith(out["base"] + "/")]
    assert len(mine) == 1 and open(mine[0]).read() == "merge", out               # the merge's folder is still there
    theirs = [m for m in out["markers"] if m.startswith(str(shared) + "/")]
    assert 1 <= len(theirs) < 5, out                                            # the shared base was pruned meanwhile


def test_pytest_base_the_full_gate_runs_make_under_a_base_of_its_own(gate):
    g = gate
    seen = g["tmp"] / "make-base.txt"
    fake(g["bin"] / "make", "make", g["calls"],
         f'echo "${{PYTEST_DEBUG_TEMPROOT:-}}" >> {seen}; [ -d "${{PYTEST_DEBUG_TEMPROOT:-/nonexistent}}" ] || exit 9\nexit 0')
    code, calls, log = run_gate(g)
    assert code == 0, log
    bases = set(seen.read_text().split())
    assert bases == {str(g["tree"]) + "-pytest"}, bases
    assert f"pytest's temp base: {g['tree']}-pytest" in log


def test_pytest_base_the_merge_removes_its_bases_with_its_trees(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    done = json.loads((w["data"] / "records/S1/merged.json").read_text())
    log = (w["data"] / "records/S1" / done["gate_run"]).read_text()
    bases = re.findall(r"pytest's temp base: (\S+)", log)
    assert len(bases) == 2, log                                                 # before and after
    gate_base = re.findall(r"gate pytest base: (\S+)", log)
    assert len(gate_base) == 1, log                                             # the full gate's, beside its tree
    assert all(not os.path.exists(b) for b in bases + gate_base), bases + gate_base
