"""The owner's file 007, line fault 14 (22 November 2026; IS5a's six red stops): the Stop hook's per-file checks read
"the files this branch changed" from the branch's merge-base with main, not from the frozen base. Measured from the
frozen base, everything a builder took in from main counted as the slice's, and a slice was held to files it never
touched (IS5a: services/api/app.py and studio_staging.py, main's, unformatted).

IS5a's shape: the slice is under way, main gains an unformatted file, the builder takes main in and stops with its own
work clean. The real ruff, as test_stop_lint.py runs it.
"""
from __future__ import annotations

from test_gates import sh, stop_gate, world  # noqa: F401  (world is a fixture)
from test_stop_lint import CLEAN_PY, branch, record, tools

MAINS = "OspreyFlow_Core/services/api/app.py"
UNFORMATTED = "def app( ):\n    return {'a':1}\n"


def main_gains(w, rel, text):
    f = w["repo"] / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    sh(["git", "add", rel], w["repo"], w["env"])
    sh(["git", "commit", "-qm", "feat: main's own, unformatted"], w["repo"], w["env"])


def test_a_file_main_brought_in_is_not_the_slices_and_never_fails_its_stop(world):
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Core/pkg/mine.py": CLEAN_PY})
    main_gains(w, MAINS, UNFORMATTED)
    sh("git merge -q --no-edit main", wt, w["env"])                       # the builder takes main in
    (wt / "OspreyFlow_Core/pkg/mine2.py").write_text(CLEAN_PY)
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'feat: more'", wt, w["env"])
    out = stop_gate(w, wt)
    assert out is None, out                                                # not held to main's file
    rec = record(w, wt)
    files = [f for r in rec["results"] if r["name"].startswith("ruff") for f in r["files"]]
    assert MAINS[len("OspreyFlow_Core/"):] not in files and "pkg/mine2.py" in files, rec["results"]


def test_the_slices_own_unformatted_file_still_fails_after_main_is_taken_in(world):
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Core/pkg/mine.py": CLEAN_PY})
    main_gains(w, "OspreyFlow_Core/other.py", CLEAN_PY)
    sh("git merge -q --no-edit main", wt, w["env"])
    (wt / "OspreyFlow_Core/pkg/bad.py").write_text(UNFORMATTED)
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'feat: bad'", wt, w["env"])
    out = stop_gate(w, wt)
    assert out and "ruff format" in out["reason"] and "pkg/bad.py" in out["reason"], out


def test_a_scan_only_mains_file_selects_is_not_run_at_the_slices_stop(world):
    w = world
    tools(w)
    (w["data"] / "bin/scan_map.tsv").write_text("# test\tprefixes\twhy\n"
                                                 "tests/test_walks_services.py\tOspreyFlow_Core/services/\twalks it\n")
    wt = branch(w, {"OspreyFlow_Core/pkg/mine.py": CLEAN_PY})
    main_gains(w, MAINS, CLEAN_PY)                                        # main's file, under the scanner's prefix
    sh("git merge -q --no-edit main", wt, w["env"])
    out = stop_gate(w, wt)
    assert out is None, out                                                # the scanner (absent here) never selected
    assert not [r for r in record(w, wt)["results"] if r["name"] == "scans"]
