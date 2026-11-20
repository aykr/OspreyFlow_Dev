"""A slice that adds a pure test which walks a folder merges without the owner editing main first, and main is never
red in between (LINE_FIXES_3_BRIEF.md, 1b).

BL6 (19 November 2026): four pure tests that each walk their own temporary repository, verified and accepted for tip
5cf1cad9ae; the suite's map check failed on the merge result because scan_map.tsv had no row for them, and a row added
to main first names tests main does not have (stale), so main's own suite goes red. Its rows cannot ride in its branch
(a commit would void the acceptance for that tip), and no agent may write scan_map.tsv.

The shape: the rows wait on main in OspreyFlow_Build/process/lanes/v062/scan_rows/<ID>.tsv (the conductor's records
mode, from rows the verifier or the owner proposed), which nothing in main's suite reads; the merge applies them in the
merge commit itself, only as added rows, each naming a test file the branch adds, and checks the map complete and not
stale on the merge result. The merge script runs here as the conductor runs it, in a throwaway repository.
"""
from __future__ import annotations

import json
import sys

from test_gates import built, main_sha, merge, sh, verified, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
MAP = "OspreyFlow_Build/scripts/slice_line/scan_map.tsv"
HEADER = "# test\tprefixes\twhy\n"
WALKER = '''import subprocess


def test_names_are_refused_in_a_repository_of_its_own(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "page.md").write_text("x\\n")
    assert [p.name for p in tmp_path.rglob("*.md")] == ["page.md"]
'''
NEW = "tests/test_client_name_check.py"
ROW = f"{NEW}\t-\twalks only its own temporary repository (tmp_path), never the checkout\n"


def state(w):
    return json.loads((w["data"] / "records/S1/state.json").read_text())


def set_state(w, **kw):
    p = w["data"] / "records/S1/state.json"
    st = json.loads(p.read_text())
    st.update(kw)
    p.write_text(json.dumps(st))


def on_main(w, files: dict, msg="docs: on main"):
    for rel, text in files.items():
        f = w["repo"] / rel
        if text is None:
            sh(["git", "rm", "-q", rel], w["repo"], w["env"])
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        sh(["git", "add", rel], w["repo"], w["env"])
    sh(["git", "commit", "-qm", msg], w["repo"], w["env"])


def checks(w, root):
    """The suite's two checks (scan_select.unmapped, scan_select.stale) on a tree's own map, as test_scans runs them."""
    code = (f"import sys, json; from pathlib import Path; sys.path.insert(0, {str(w['lines'])!r}); import scan_select as s; "
            f"b = Path({str(root)!r}) / 'OspreyFlow_Build'; t = s.load((b / 'scripts/slice_line/scan_map.tsv').read_text()); "
            "print(json.dumps([s.unmapped(b, t), s.stale(b, t)]))")
    return json.loads(sh([w["py"], "-c", code], w["repo"], w["env"]).stdout)


def with_map(w, rows=""):
    on_main(w, {MAP: HEADER + rows}, "chore: the line's scan map")


def walker_slice(w, extra=None):
    wt, tip = built(w, extra={f"OspreyFlow_Build/{NEW}": WALKER, **(extra or {})})
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    return wt, tip


def test_scan_rows_a_branch_adding_a_pure_walker_with_no_row_is_refused_in_words_naming_it(world):
    w = world
    with_map(w)
    wt, tip = walker_slice(w)
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and NEW in p.stderr and "scan_rows/S1.tsv" in p.stderr and "Traceback" not in p.stderr, \
        p.stderr
    assert main_sha(w) == before and state(w)["phase"] == "verified"            # not the slice's fault: not recorded


def test_scan_rows_recorded_on_main_merge_with_the_tip_unchanged_and_main_is_never_red(world):
    w = world
    with_map(w)
    wt, tip = walker_slice(w)
    on_main(w, {f"{V062}/scan_rows/S1.tsv": HEADER + ROW}, "docs(process): S1's scan rows")
    assert checks(w, w["repo"]) == [[], []]                                     # main alone: green with rows waiting
    # the plant: the same rows written into main's map before the merge name a test main has not got: stale is red
    probe = w["tmp"] / "probe"
    sh(["git", "worktree", "add", "-q", "--detach", str(probe), "main"], w["repo"], w["env"])
    (probe / MAP).write_text(HEADER + ROW)
    assert checks(w, probe)[1] == [f"{NEW}: no such test"]
    sh(["git", "worktree", "remove", "--force", str(probe)], w["repo"], w["env"])
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    done = json.loads((w["data"] / "records/S1/merged.json").read_text())
    assert done["tip"] == tip and done["scan_rows"] == [ROW.rstrip("\n")], done   # the accepted tip, as it was
    assert (w["repo"] / MAP).read_text() == HEADER + ROW
    assert not (w["repo"] / V062 / "scan_rows/S1.tsv").exists()
    assert sh(["git", "rev-parse", "main^2"], w["repo"], w["env"]).stdout.strip() == tip   # still a merge of that tip
    assert checks(w, w["repo"]) == [[], []]                                     # main after: green


def test_scan_rows_a_row_naming_a_test_the_branch_does_not_add_is_refused(world):
    w = world
    with_map(w)
    wt, tip = walker_slice(w)
    other = "tests/test_somebody_elses.py\t-\twalks only its own temporary folder\n"
    on_main(w, {f"{V062}/scan_rows/S1.tsv": HEADER + ROW + other})
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "tests/test_somebody_elses.py" in p.stderr and "does not add" in p.stderr, p.stderr
    assert main_sha(w) == before


def test_scan_rows_a_row_that_edits_one_already_in_the_map_is_refused(world):
    w = world
    with_map(w, ROW)
    on_main(w, {f"OspreyFlow_Build/{NEW}": WALKER}, "test: an older walker")
    wt, tip = walker_slice(w, extra={f"OspreyFlow_Build/{NEW}": WALKER + "\n# more\n"})
    on_main(w, {f"{V062}/scan_rows/S1.tsv": HEADER + f"{NEW}\tOspreyFlow_Core/\twalks the core now\n"})
    p = merge(w)
    assert p.returncode == 1 and NEW in p.stderr and "already" in p.stderr, p.stderr


def test_scan_rows_a_row_with_no_reason_is_refused(world):
    w = world
    with_map(w)
    walker_slice(w)
    on_main(w, {f"{V062}/scan_rows/S1.tsv": HEADER + f"{NEW}\t-\t \n"})
    p = merge(w)
    assert p.returncode == 1 and "why" in p.stderr and NEW in p.stderr, p.stderr


def test_scan_rows_a_branch_removing_a_mapped_test_is_refused_naming_its_stale_row(world):
    w = world
    with_map(w, ROW)
    on_main(w, {f"OspreyFlow_Build/{NEW}": WALKER}, "test: a walker")
    wt, tip = built(w)
    sh(["git", "rm", "-q", f"OspreyFlow_Build/{NEW}"], wt, w["env"])
    sh(["git", "commit", "-qm", "refactor: drop a test"], wt, w["env"])
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and f"{NEW}: no such test" in p.stderr, p.stderr
    assert main_sha(w) == before


def test_scan_rows_on_a_slices_branch_are_a_protected_path(world):
    """A builder's rows never reach the merge from its own branch: the rows file is the conductor's records."""
    w = world
    with_map(w)
    wt, tip = walker_slice(w, extra={f"{V062}/scan_rows/S1.tsv": HEADER + ROW})
    p = merge(w)
    assert p.returncode == 1 and "protected" in p.stderr and "scan_rows" in p.stderr, p.stderr
