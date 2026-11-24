"""Item 4 (the owner's approval, 23 November 2026): the server's green stands across records commits. Before it, any
commit to main after the server's run voided the result, the conductor's ordinary records commits included, and the
whole gate ran again (35 minutes). Now a result stands when main has moved since the run only by records commits, by the
rule land() already lands a merge by: each a Slice-Records commit with one parent, together changing only files in the
records folder that are not scan rows, the owner's own files or a file the slice changed; the server's candidate, made
again here from the server's main and the slice's tip, is the tree the server gives; and the Mac's candidate differs
from it in exactly those files, each as main has it. The Mac then still runs every target that reads the records
folder (the owner's approved list): slice-line-check, citation-check, client-name-check, live-collect, every test whose
scan_map.tsv row covers the folder, and test_live_select.py. Anything else that moved main runs the whole gate, as
before.
"""
from __future__ import annotations

import json

import pytest

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_counts import X, Y, gate_plan, green
from test_gates import built, verified
from test_server_slot import FAKE_EW, RID, V062, note, switch

CI = "ci: core-check slice-line-check citation-check client-name-check lint-tools\n"
CHECK = "check: lint typecheck\n"
PASSED = ["slice-line-check", "citation-check", "client-name-check", "lint-tools", "lint", "typecheck", "test"]
NOTE = f"{V062}/S9_ROUND_TABLE_2026-11-24.md"                       # a records file: none of the line's own


def makefiles(w):
    (w["repo"] / "OspreyFlow_Build/Makefile").write_text(CI)
    (w["repo"] / "OspreyFlow_Core/Makefile").write_text(CHECK)
    sh("git add -A OspreyFlow_Build/Makefile OspreyFlow_Core/Makefile && git commit -qm 'ci targets'", w["repo"], w["env"])


def ready(w, extra=None):
    """test_server_slot.ready, with files of the slice's own (extra)."""
    wt, tip = built(w, extra=extra)
    verified(w, wt, tip)
    p = w["data"] / "records/S1/state.json"
    st = json.loads(p.read_text())
    st.update(phase="verified", tip=tip)
    p.write_text(json.dumps(st))
    (w["lines"] / "early_warning.py").write_text(FAKE_EW)
    sh("git add OspreyFlow_Build/scripts/slice_line/early_warning.py && git commit -qm 'test: the early warning stood in'",
       w["repo"], w["env"])
    w["env"]["TEST_EW_RESULTS"] = str(w["tmp"] / "ew")
    (w["tmp"] / "ew").mkdir(exist_ok=True)
    return wt, tip


def setup(w, extra=None):
    makefiles(w)
    wt, tip = ready(w, extra)
    switch(w, "on\n")
    note(w, tip, headline="GREEN")
    green(w, tip, passed_targets=PASSED)                           # the server's run, on main as it is now
    return wt, tip


def commit(w, files, message="docs(slice-line): S9's round table", records=True):
    for path, text in files.items():
        f = w["repo"] / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    sh(["git", "add", "-A", "--", *files], w["repo"], w["env"])
    sh(["git", "commit", "-q", "-m", message + ("\n\nSlice-Records: yes" if records else "")], w["repo"], w["env"])


def test_a_green_stands_across_a_records_commit_and_the_mac_runs_what_reads_the_records_folder(world):
    w = world
    wt, tip = setup(w)
    commit(w, {NOTE: "S9's round table\n"})                         # the conductor's ordinary records commit
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert server["counted"] is True and server["run_id"] == RID, server
    assert server["records_moved"] == [NOTE], server
    assert plan[0] == ["make", "-k", "slice-line-check", "citation-check", "client-name-check"], plan
    assert ["make", "live-collect"] in plan, plan
    files = next(t for t in plan if "server-test-files" in t)[-1].split("=", 1)[1].split()
    for f in (f"../{X}", f"../{Y}", "../OspreyFlow_Build/tests/test_live_select.py",
              "../OspreyFlow_Build/tests/test_doc_citations_check.py",
              "../OspreyFlow_Build/tests/test_client_name_check.py"):
        assert f in files, (f, files)
    assert server["taken"] == ["lint-tools", "core:lint", "core:typecheck", "test"], server   # never a records reader


def test_two_records_commits_stand_and_name_both_files(world):
    w = world
    wt, tip = setup(w)
    commit(w, {NOTE: "S9's round table\n"})
    commit(w, {f"{V062}/MORNING_2026-11-24.md": "morning\n"}, "docs(slice-line): the morning note")
    p, plan, server = gate_plan(w)
    assert server["counted"] is True and server["records_moved"] == sorted([NOTE, f"{V062}/MORNING_2026-11-24.md"])


@pytest.mark.parametrize("how,why", [
    ("not-a-records-commit", "which is not a records commit"),
    ("records-trailer-outside-the-folder", "in a path the server's run tested"),
    ("a-scan-row", "in a path the server's run tested"),
    ("an-owners-file", "in a path the server's run tested"),
    ("a-file-the-slice-changed", "in a path the server's run tested"),
    ("a-merge-commit", "which is not a records commit"),
    ("the-servers-tree-is-not-its-candidate", "cannot be made again here"),
    ("main-not-forward", "and not forward")])
def test_anything_else_moving_main_runs_the_whole_gate(world, how, why):
    w = world
    if how == "a-file-the-slice-changed":
        lines = [f"line {i}\n" for i in range(9)]
        commit(w, {NOTE: "".join(lines),                                    # on main before the slice starts
                   "OspreyFlow_Build/scripts/slice_line/scan_map.tsv": "# no rows: the slice's scans are not this case\n"},
               "docs: a table both change", records=False)
        wt, tip = setup(w, extra={NOTE: "".join(["the slice's own word\n", *lines[1:]])})
        green(w, tip, passed_targets=PASSED)
        commit(w, {NOTE: "".join([*lines[:8], "the conductor's word\n"])})   # merges cleanly; the slice changed it
    else:
        wt, tip = setup(w)
    if how == "not-a-records-commit":
        commit(w, {NOTE: "x\n"}, records=False)
    elif how == "records-trailer-outside-the-folder":
        commit(w, {"OspreyFlow_Build/tests/test_new.py": "def test_x():\n    assert True\n"})
    elif how == "a-scan-row":
        commit(w, {f"{V062}/scan_rows/S9.tsv": "tests/test_x.py\tOspreyFlow_Build/\twalks\n"})
    elif how == "an-owners-file":
        commit(w, {f"{V062}/dial.yaml": (w["repo"] / V062 / "dial.yaml").read_text() + "# a note\n"})
    elif how == "a-merge-commit":
        sh("git checkout -q -b side main~1 && git commit -q --allow-empty -m side && git checkout -q main", w["repo"],
           w["env"])
        sh(["git", "merge", "-q", "--no-ff", "side", "-m", "records\n\nSlice-Records: yes"], w["repo"], w["env"])
    elif how == "the-servers-tree-is-not-its-candidate":
        r = json.loads((w["tmp"] / "ew" / f"{RID}.json").read_text())
        r["tree"] = sh(["git", "rev-parse", "main^{tree}"], w["repo"]).stdout.strip()   # a real tree, not its candidate
        (w["tmp"] / "ew" / f"{RID}.json").write_text(json.dumps(r))
        commit(w, {NOTE: "x\n"})
    elif how == "main-not-forward":
        r = json.loads((w["tmp"] / "ew" / f"{RID}.json").read_text())
        sh("git checkout -q -b gone main && git commit -q --allow-empty -m gone && git checkout -q main", w["repo"],
           w["env"])
        r["main"] = sh("git rev-parse gone", w["repo"]).stdout.strip()
        (w["tmp"] / "ew" / f"{RID}.json").write_text(json.dumps(r))
    p, plan, server = gate_plan(w)
    assert plan is None, (how, plan, p.stdout[-600:], p.stderr[-2500:])  # the whole gate, as before
    assert server["counted"] is False and why in server["why"], (how, server)
    assert "main has moved since the server's run" in server["why"], server
