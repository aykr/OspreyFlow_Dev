"""Any merge conflict with main is recorded, and a send-back for it is free (LINE_FIXES_3_BRIEF.md, 1a).

GG6 (19 November 2026): verified at 496d7b92ce, and both it and main had appended a row at the end of the table in
OspreyFlow_Build/spec/ADR_RESERVATIONS.md. The merge refused it ("the builder rebases it") and recorded nothing, so the
slice stayed `verified` and resume.py refused every way back. The merge and resume.py run here as the conductor runs
them, in a throwaway repository, with the same conflict: one row appended on main, another on the branch.
"""
from __future__ import annotations

import json
import time

from test_gates import built, main_sha, merge, sh, stop_gate, verified, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
TODAY = time.strftime("%Y-%m-%d", time.gmtime())
#: GG6's table is OspreyFlow_Build/spec/ADR_RESERVATIONS.md; here the same table sits where no scanner of the real
#: scan map is selected, so the Stop hook and the merge run only what the conflict is about.
TABLE = "notes/ADR_RESERVATIONS.md"
HEAD = "# ADR reservations\n\n| ADR | Slice | Reserved |\n| --- | --- | --- |\n| ADR-200 | AA1 | 2026-11-17 |\n"
OURS = "| ADR-201 | S1 | 2026-11-18 |\n"
MAINS = "| ADR-202 | XX9 | 2026-11-19 |\n"


def state(w):
    return json.loads((w["data"] / "records/S1/state.json").read_text())


def set_state(w, **kw):
    p = w["data"] / "records/S1/state.json"
    st = json.loads(p.read_text())
    st.update(kw)
    p.write_text(json.dumps(st))


def resume(w, action="send-back"):
    return sh([w["py"], str(w["lines"] / "resume.py"), "S1", action], w["repo"], w["env"], check=False)


def changes(w):
    f = w["data"] / "owner-changes.tsv"
    return [ln.split("\t") for ln in f.read_text().splitlines()[1:]] if f.exists() else []


def table_on_main(w, text):
    f = w["repo"] / TABLE
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    sh(["git", "add", TABLE], w["repo"], w["env"])
    sh(["git", "commit", "-qm", "docs: reserve an ADR"], w["repo"], w["env"])


def conflicted(w):
    """S1 verified at a tip that appends a row; main has since appended another: the merge is refused."""
    table_on_main(w, HEAD)
    wt, tip = built(w, extra={TABLE: HEAD + OURS})
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    table_on_main(w, HEAD + MAINS)
    return wt, tip


def test_a_conflict_outside_the_records_folder_is_recorded_with_the_files_merge_tree_names(world):
    w = world
    wt, tip = conflicted(w)
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and TABLE in p.stderr and "send-back" in p.stderr, p.stderr
    assert main_sha(w) == before
    st = state(w)
    assert (st["phase"], st["refused_for"], st["refused_tests"]) == ("refused", "conflict", 0), st
    rec = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())
    assert rec["verdict"] == "findings" and rec["commit"] == tip and len(rec["findings"]) == 1, rec
    f = rec["findings"][0]
    assert f["file"] == TABLE and TABLE in f["what"] and "both" in f["what"] and "merge-tree" in f["evidence"], f
    board = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    row = next(ln for ln in board.stdout.splitlines() if ln.startswith("S1 "))
    assert "conflict" in row, board.stdout


def test_a_conflict_send_back_works_at_the_rounds_limit_with_no_line_and_spends_no_round(world):
    w = world
    wt, tip = conflicted(w)
    merge(w)
    lim = state(w)["rounds_limit"]
    set_state(w, round=lim)                                                    # GG6: round 5 of 5
    assert not (w["repo"] / V062 / "resume.tsv").exists()                      # no add-round line
    p = resume(w)
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert (st["phase"], st["round"], st["rounds_limit"]) == ("building", lim, lim), st
    log = changes(w)
    assert len(log) == 1 and log[0][2] == "send-back" and "conflict" in log[0][3] and "round unchanged" in log[0][3], log
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import run_seat; "
            "print(run_seat.last_findings('S1'))")
    assert TABLE in sh([w["py"], "-c", code], w["repo"], w["env"]).stdout     # the builder's prompt names the file
    # the builder's one task: merge main in, keeping both rows; then the verifier passes the new tip and it merges
    m = sh("git merge -q main", wt, w["env"], check=False)
    assert m.returncode != 0 and "CONFLICT" in m.stdout + m.stderr
    (wt / TABLE).write_text(HEAD + MAINS + OURS)
    sh(f"git add {TABLE} && git commit -q --no-edit", wt, w["env"])
    assert stop_gate(w, wt) is None
    tip2 = sh("git rev-parse HEAD", wt).stdout.strip()
    assert sh(["git", "merge-tree", "--write-tree", "main", tip2], w["repo"], w["env"], check=False).returncode == 0
    verified(w, wt, tip2)
    set_state(w, phase="verified", tip=tip2)
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert (w["repo"] / TABLE).read_text() == HEAD + MAINS + OURS
    assert state(w)["round"] == lim


def test_a_merge_that_fails_with_no_file_named_by_merge_tree_is_refused_in_words_and_not_recorded(world):
    """A merge refused by something other than a conflict (here a pre-merge-commit hook): git merge-tree names no
    file, so it is not the slice's fault: nothing recorded, the slice left where it was."""
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    hook = w["repo"] / ".git/hooks/pre-merge-commit"
    hook.write_text("#!/bin/sh\necho 'refused by a hook' >&2\nexit 1\n")
    hook.chmod(0o755)
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "names no conflicting file" in p.stderr and "Traceback" not in p.stderr, p.stderr
    assert main_sha(w) == before
    st = state(w)
    assert st["phase"] == "verified" and "refused_for" not in st, st
    assert not (w["data"] / f"records/S1/verify-gate-{tip}.json").exists()


def test_a_records_only_conflict_keeps_its_own_kind(world):
    """The records-only case is unchanged: kind `records`, and send-back merges main in, taking main's records."""
    w = world
    rules = w["repo"] / V062 / "RULINGS.md"
    rules.write_text("# Rulings\n")
    sh(f"git add {V062}/RULINGS.md && git commit -qm 'docs: rulings' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    wt, tip = built(w, extra={f"{V062}/RULINGS.md": "# Rulings\n\nthe branch's copy\n"})
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    rules.write_text("# Rulings\n\nmain's newer text\n")
    sh("git commit -qam 'docs: newer rulings' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    p = merge(w)
    assert p.returncode == 1 and state(w)["refused_for"] == "records", p.stderr
    p = resume(w)
    assert p.returncode == 0 and (wt / V062 / "RULINGS.md").read_text() == "# Rulings\n\nmain's newer text\n"
