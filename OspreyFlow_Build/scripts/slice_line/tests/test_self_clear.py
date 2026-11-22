"""The line clears a stop itself (LINE_FIXES_5_BRIEF.md, A; the owner's "fewer stops for my lines", 21 November 2026).

Two causes, each tested so it cannot be stretched: (b) the red stop's failing check is one the slice did not write and it
fails identically on main's own tree made as a builder's worktree is made (the `test_layout` case: the rulings copy at
the worktree's root); then the line removes that check from the slice's row (recorded, committed, refrozen) and never
the acceptance; (a) main has moved under the slice, merges into the branch cleanly and changes none of the slice's own
acceptance files; then the line merges it in. Whatever the cause, the line never clears a stop at the eighth round, a
stop naming a key, a credential or a security rule, a stop on a verifier's findings (a fault, or open findings only the
owner accepts) or one whose frozen commands wait on a refreeze. Each clearance is logged in the slice's folder and in
self-clears.tsv, which the board prints for the conductor's morning report.

Each case runs resume.py as the conductor runs it, in a throwaway repository shaped like this one, with the slice started
by slice_start.py and stopped as the line stops it.
"""
from __future__ import annotations

import json
import sys
import time

import pytest

from test_gates import sh, started, stop_gate, world  # noqa: F401  (world is a fixture)
from test_resume import V062, changes, owner_line, resume, said_refused, set_state, snapshot, state

PY = sys.executable
TODAY = time.strftime("%Y-%m-%d", time.gmtime())
#: tests/test_layout.py's case, in small: a product folder left at the root of the tree fails it.
LAYOUT_STAND_IN = '''from pathlib import Path


def test_no_product_folder_is_left_at_the_root():
    root = Path(__file__).resolve().parents[1]
    stray = sorted(p.name for p in root.iterdir() if p.name == "Claude outputs")
    assert not stray, f"still at the root: {stray}"
'''
#: A check that fails only in a tree made as a builder's worktree is made, as test_layout did on the rulings copy until
#: the line moved it into the worktree's git folder (5): here, on the hashed client-name list, which the line copies into
#: every worktree where git ignores it (the main checkout keeps it; a fresh tree has none).
HASHES = "OspreyFlow_Build/marketing_site/client_names.local.sha256"
LAYOUT = '''from pathlib import Path

HASHES = "OspreyFlow_Build/marketing_site/client_names.local.sha256"


def test_no_product_folder_is_left_at_the_root():
    root = Path(__file__).resolve().parents[1]
    stray = sorted(p.name for p in root.iterdir() if p.name == "Claude outputs")
    stray += [HASHES.rsplit(".", 1)[0]] if (root / HASHES).exists() else []  # its name alone (no hash words)
    assert not stray, f"left in the tree: {stray}"


def test_the_readme_is_there():
    assert (Path(__file__).resolve().parents[1] / "README.md").is_file()
'''
PYTEST = f"{PY} -m pytest -q -p no:cacheprovider --rootdir=."
CHECKS = f"true && {PYTEST} tests/test_layout.py && echo checked"
LAYOUT_ID = "tests/test_layout.py::test_no_product_folder_is_left_at_the_root"
RED_NOTE = "the builder could not get the checks green in 6 tries: narrow the slice, or change its checks (your word)?"


def commit_main(w, files: dict, msg="docs(process): records"):
    for rel, text in files.items():
        (w["repo"] / rel).parent.mkdir(parents=True, exist_ok=True)
        (w["repo"] / rel).write_text(text)
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm \"$M\" --trailer 'Slice-Records: yes'",
       w["repo"], {**w["env"], "M": msg})
    return sh("git rev-parse HEAD", w["repo"]).stdout.strip()


def set_row(w, acceptance="sh accept.sh", checks=CHECKS, files="accept.sh"):
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("S1\tCO1\tA test slice\t-\t1\t-\tnone\taccept.sh\tsh accept.sh\ttrue",
                                           f"S1\tCO1\tA test slice\t-\t1\t-\tnone\t{files}\t{acceptance}\t{checks}"))


def layout_slice(w, acceptance="sh accept.sh", files="accept.sh"):
    """S1, its checks running the layout test, started while main has no RULINGS.md (so no copy at the root), its work
    committed green. Returns the worktree."""
    set_row(w, acceptance=acceptance, files=files)
    gi = (w["repo"] / ".gitignore").read_text()
    commit_main(w, {"tests/test_layout.py": LAYOUT, ".gitignore": gi + HASHES + "\n"}, "docs: S1 and the layout test")
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    (wt / "accept.sh").write_text("exit 0\n")
    sh("git add accept.sh && git commit -qm 'feat: S1'", wt, w["env"])
    return wt


def hashes_in_the_main_checkout(w):
    """The hashed client-name list in the main checkout, where git ignores it, as on the owner's Mac."""
    gi = w["repo"] / ".gitignore"
    if HASHES not in gi.read_text():
        commit_main(w, {".gitignore": gi.read_text() + HASHES + "\n"}, "chore: the hashed list is never committed")
    (w["repo"] / HASHES).parent.mkdir(parents=True, exist_ok=True)
    (w["repo"] / HASHES).write_text("0" * 64 + "\n")


def rulings_reach_the_worktree(w, wt):
    """The worktree-only file reaches the worktree as the line brings it (slice_start.py's copy of the hashed list)."""
    hashes_in_the_main_checkout(w)
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import slice_start; from pathlib import Path; "
            f"print(slice_start.bring_client_hashes(Path({str(wt)!r})))")
    assert "was copied" in sh([w["py"], "-c", code], w["repo"], w["env"]).stdout


def red_six_times(w, wt):
    for _ in range(6):
        stop_gate(w, wt)
    assert (w["data"] / "records/S1/red_stop.json").exists()
    set_state(w, phase="stopped", note=RED_NOTE)


def red_stop(w, wt, *last, **st):
    """The Stop hook's red-stop record for the worktree's tip, written as stop_check.py writes it, and the stop."""
    rec = w["data"] / "records/S1"
    sha = sh("git rev-parse HEAD", wt).stdout.strip()
    (rec / "red_stop.json").write_text(json.dumps({"slice": "S1", "commit": sha, "red_stops": 6, "at": "2026-11-21T00:00:00Z",
                                                   "last": list(last)}, indent=1))
    (rec / "red_stops").write_text("6")
    set_state(w, phase="stopped", note=RED_NOTE, **st)


def acceptance_red(cmd="sh accept.sh"):
    return f"RED: acceptance (exit 1): {cmd}\nFAILED tests/test_a.py::test_x - AssertionError: no"


def a_slice_red_on_its_own(w):
    """S1 red on its own acceptance (the Stop hook's six stops), then main moves: what cause (a) is for."""
    wt = layout_slice(w)
    (wt / "accept.sh").write_text("echo 'FAILED tests/test_a.py::test_x - AssertionError: no'; exit 1\n")
    sh("git add accept.sh && git commit -qm 'test: red'", wt, w["env"])
    red_six_times(w, wt)
    commit_main(w, {f"{V062}/notes.md": "a conductor's note\n"})
    return wt


def clears(w):
    f = w["data"] / "self-clears.tsv"
    return [dict(zip(f.read_text().splitlines()[0].split("\t"), ln.split("\t")))
            for ln in f.read_text().splitlines()[1:]] if f.exists() else []


def unchanged(w, wt, before, heads):
    assert snapshot(w) == before
    assert (sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout) == heads
    assert clears(w) == [] and not list((w["data"] / "records/S1").glob("self-clear-*.json"))


def frozen(w):
    return json.loads((w["data"] / "records/S1/frozen.json").read_text())


def board_says(w):
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"])
    status = w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js"
    body = json.loads(status.read_text().split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    return p.stdout, body


# ------------------------------------------------------------------ the two causes


def test_cause_b_a_check_the_slice_did_not_write_failing_identically_on_main_is_removed_and_the_stop_cleared(world):
    """The test_layout case (PL4d3c, 21 November): the rulings copy at the worktree's root fails a layout test the slice
    never touched; on main's own tree, made as a builder's worktree is made, it fails the same way."""
    w = world
    wt = layout_slice(w)
    rulings_reach_the_worktree(w, wt)
    red_six_times(w, wt)
    last = json.loads((w["data"] / "records/S1/red_stop.json").read_text())["last"]
    assert len(last) == 1 and last[0].startswith("RED: checks") and LAYOUT_ID in last[0], last
    p = resume(w, "S1", "self-clear")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "cleared by the line (cause b)" in p.stdout and LAYOUT_ID in p.stdout, p.stdout
    narrowed = f"true && {PYTEST} tests/test_layout.py --deselect {LAYOUT_ID} && echo checked"
    fz = frozen(w)
    assert fz["checks"] == narrowed and fz["acceptance"] == "sh accept.sh", fz
    assert fz["history"][-1]["checks"] == CHECKS and fz["refrozen_by"].startswith("line (self-clear, cause b)"), fz
    row = sh(["git", "show", f"main:{V062}/slices.tsv"], w["repo"]).stdout
    assert f"\t{narrowed}\n" in row, row  # main's row and the frozen record agree: the merge's frozen match holds
    log = sh("git log -1 --format=%B main", w["repo"]).stdout
    assert "Slice-Records: yes" in log and LAYOUT_ID in log, log
    st = state(w)
    assert st["phase"] == "building" and st["round"] == 1 and "note" not in st, st
    assert not (w["data"] / "records/S1/red_stop.json").exists()
    (row1,) = clears(w)
    assert (row1["slice"], row1["stop"], row1["cause"]) == ("S1", "red", "b") and LAYOUT_ID in row1["what"], row1
    (rec,) = list((w["data"] / "records/S1").glob("self-clear-*.json"))
    assert json.loads(rec.read_text())["cause"] == "b"
    assert changes(w) == []  # no owner's line was used
    assert stop_gate(w, wt) is None  # the builder's next stop: green on the narrowed checks
    assert json.loads((w["data"] / f"records/S1/tests-{sh('git rev-parse HEAD', wt).stdout.strip()}.json").read_text())["green"]


def test_cause_a_main_moved_under_the_slice_is_merged_in_and_the_stop_cleared_once_per_move(world):
    w = world
    wt = a_slice_red_on_its_own(w)
    main = sh("git rev-parse main", w["repo"]).stdout.strip()
    p = resume(w, "S1", "self-clear")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "cleared by the line (cause a)" in p.stdout, p.stdout
    assert sh(["git", "merge-base", "--is-ancestor", main, "HEAD"], wt, check=False).returncode == 0  # main is in
    assert frozen(w)["checks"] == CHECKS and "history" not in frozen(w)  # nothing about what is tested changed
    st = state(w)
    assert st["phase"] == "building" and st["round"] == 1, st
    (row1,) = clears(w)
    assert (row1["stop"], row1["cause"]) == ("red", "a") and main in row1["what"], row1
    red_six_times(w, wt)  # red again on its own work, main where it was: not cleared again
    before, heads = snapshot(w), (sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "main has not moved", "not one the line clears"), p.stdout + p.stderr
    assert snapshot(w) == before and len(clears(w)) == 1 and sh("git rev-parse HEAD", wt).stdout == heads[0]


def test_the_log_lists_every_clearance_and_the_board_prints_it(world):
    w = world
    wt = a_slice_red_on_its_own(w)
    assert resume(w, "S1", "self-clear").returncode == 0
    red_six_times(w, wt)
    commit_main(w, {f"{V062}/notes.md": "another note\n"})  # main moves again: a second clearance
    p = resume(w, "S1", "self-clear")
    assert p.returncode == 0, p.stdout + p.stderr
    rows = clears(w)
    assert [(r["slice"], r["cause"]) for r in rows] == [("S1", "a"), ("S1", "a")], rows
    assert len(list((w["data"] / "records/S1").glob("self-clear-*.json"))) == 2
    out, body = board_says(w)
    said = [ln for ln in out.splitlines() if ln.startswith("cleared by the line: S1 (red stop, cause a)")]
    assert len(said) == 2, out
    assert [r["cause"] for r in body["self_clears"]] == ["a", "a"], body["self_clears"]
    p = sh([w["py"], str(w["lines"] / "board.py"), "--self-clears"], w["repo"], w["env"])
    assert len(p.stdout.strip().splitlines()) == 2 and all(r["what"] in p.stdout for r in rows), p.stdout


def test_a_red_stop_with_neither_cause_waits_for_the_owner(world):
    w = world
    wt = layout_slice(w)
    (wt / "accept.sh").write_text("exit 1\n")
    sh("git add accept.sh && git commit -qm 'test: red'", wt, w["env"])
    red_six_times(w, wt)  # main has not moved; the acceptance is red: the slice's own red
    before, heads = snapshot(w), (sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "not one the line clears", "not (b)", "not (a)", "main has not moved"), p.stdout + p.stderr
    unchanged(w, wt, before, heads)


# ------------------------------------------------------------------ never the line's: the owner's alone


def test_a_stop_at_the_eighth_round_is_never_cleared_by_the_line(world):
    w = world
    wt = a_slice_red_on_its_own(w)  # cause (a) holds
    set_state(w, round=8, rounds_limit=8)
    before, heads = snapshot(w), (sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "round 8", "eighth round", "owner's alone"), p.stdout + p.stderr
    unchanged(w, wt, before, heads)


@pytest.mark.parametrize("words", ["FAILED tests/test_a.py::test_the_api_key_is_never_logged - AssertionError: printed",
                                   "E   AssertionError: the credential store was readable",
                                   "FAILED tests/test_a.py::test_x - the guard's SECURITY rule 4 did not refuse"],
                         ids=["key", "credential", "security-rule"])
def test_a_stop_naming_a_key_a_credential_or_a_security_rule_is_never_cleared_by_the_line(world, words):
    w = world
    wt = a_slice_red_on_its_own(w)  # cause (a) holds
    red_stop(w, wt, f"RED: acceptance (exit 1): sh accept.sh\n{words}")
    before, heads = snapshot(w), (sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "a key, a credential or a security rule", "never clears"), p.stdout + p.stderr
    unchanged(w, wt, before, heads)


def test_a_security_word_in_the_echoed_command_alone_does_not_hold_a_stop(world):
    """The red stop echoes the whole command (PL4d3c's names test_design_tokens_location.py): only the failure lines
    are read, or no real slice could ever be cleared."""
    w = world
    wt = a_slice_red_on_its_own(w)
    red_stop(w, wt, acceptance_red("sh accept.sh tests/test_design_tokens_location.py"))
    p = resume(w, "S1", "self-clear")
    assert p.returncode == 0 and "cause a" in p.stdout, p.stdout + p.stderr


@pytest.mark.parametrize("how", ["row-changed", "line-waiting"])
def test_a_refreeze_that_changes_what_is_tested_is_never_the_lines(world, how):
    w = world
    wt = a_slice_red_on_its_own(w)  # cause (a) holds
    if how == "row-changed":  # the conductor's new checks on main, waiting on the owner's refreeze
        tsv = w["repo"] / V062 / "slices.tsv"
        commit_main(w, {f"{V062}/slices.tsv": tsv.read_text().replace(f"\t{CHECKS}\n", "\ttrue\n")})
    else:
        owner_line(w, f"S1\trefreeze\t{TODAY}")
    before, heads = snapshot(w), (sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "a refreeze changes what is tested", "owner's alone"), p.stdout + p.stderr
    unchanged(w, wt, before, heads)


def findings_stop(w, wt, *kinds):
    """S1 stopped at its rounds limit on its verifier's findings for its tip, of these kinds; main moved since."""
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    rec = w["data"] / "records/S1"
    (rec / f"tests-{tip}.json").write_text(json.dumps({"slice": "S1", "commit": tip, "green": True}))
    findings = [{"file": "x.py", "line": 1, "what": f"finding {n}", "evidence": "read", "kind": k}
                for n, k in enumerate(kinds)]
    (rec / f"verify-{tip}.json").write_text(json.dumps({"slice": "S1", "commit": tip, "verdict": "findings",
                                                         "passes": [], "findings": findings}))
    set_state(w, phase="stopped", round=2, rounds_limit=2,
              note="findings after 2 round(s): accept a narrower slice, or allow another round?")
    commit_main(w, {f"{V062}/notes.md": "main moved\n"})


def test_accepting_a_slice_with_open_findings_is_never_the_lines(world):
    w = world
    wt = layout_slice(w)
    findings_stop(w, wt, "test_gap", "test_gap")
    before, heads = snapshot(w), (sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "accepting a slice with open findings", "never the line's"), p.stdout + p.stderr
    unchanged(w, wt, before, heads)
    assert not list((w["data"] / "records/S1").glob("accepted-*.json")) and state(w)["phase"] == "stopped"


@pytest.mark.parametrize("kinds", [("fault",), ("fault", "test_gap"), (None,)], ids=["fault", "fault-and-gap", "no-kind"])
def test_a_stop_with_a_finding_of_fault_in_behaviour_is_not_cleared(world, kinds):
    w = world
    wt = layout_slice(w)
    findings_stop(w, wt, *kinds)
    before, heads = snapshot(w), (sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "a fault in behaviour", "never clears"), p.stdout + p.stderr
    unchanged(w, wt, before, heads)


def test_cause_b_never_removes_the_acceptance_test(world):
    """The acceptance is red first, on main too: identical on main, and still never removed."""
    w = world
    accept = f"sh accept.sh && {PYTEST} tests/test_layout.py"
    wt = layout_slice(w, acceptance=accept)
    rulings_reach_the_worktree(w, wt)
    red_stop(w, wt, f"RED: checks (exit 1): {CHECKS}\nFAILED {LAYOUT_ID} - AssertionError: still at the root")
    p = resume(w, "S1", "self-clear")
    out = p.stdout + p.stderr
    assert "the acceptance is never removed" in out or "cause a" in out, out
    assert frozen(w)["checks"] == CHECKS  # never narrowed: (a) may merge main in, (b) never removes the acceptance's test
    assert all(r["cause"] != "b" for r in clears(w))


def test_cause_b_never_removes_a_check_the_slice_changed(world):
    w = world
    wt = layout_slice(w)
    (wt / "tests/test_layout.py").write_text(LAYOUT + "\n# the slice's own change\n")
    sh("git add -A tests && git commit -qm 'test: the slice changes the layout test'", wt, w["env"])
    rulings_reach_the_worktree(w, wt)
    red_six_times(w, wt)
    p = resume(w, "S1", "self-clear")
    out = p.stdout + p.stderr
    assert "in a file the slice wrote or changed" in out or "cause a" in out, out
    assert frozen(w)["checks"] == CHECKS  # never removed: (a) may merge main in, (b) never narrows it
    assert all(r["cause"] != "b" for r in clears(w))


def test_cause_b_needs_the_same_failure_on_mains_own_tree(world):
    """A check red in the worktree only (the slice's own doing, outside git's view) is not (b)."""
    w = world
    wt = layout_slice(w)
    (wt / "Claude outputs").mkdir()  # main never gets this: on main's tree the layout test is green
    (wt / "Claude outputs/stray.txt").write_text("x\n")
    red_six_times(w, wt)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "does not fail identically on main"), p.stdout + p.stderr
    assert frozen(w)["checks"] == CHECKS and clears(w) == []


def test_the_owners_actions_are_unchanged_by_self_clear(world):
    """clear-stop still needs the owner's line: self-clear is a separate action, never a way round it."""
    w = world
    wt = layout_slice(w)
    (wt / "accept.sh").write_text("exit 1\n")
    sh("git add accept.sh && git commit -qm 'test: red'", wt, w["env"])
    red_six_times(w, wt)
    p = resume(w, "S1", "clear-stop")
    assert said_refused(p, "no line", "resume.tsv"), p.stdout + p.stderr


def test_run_seat_tries_the_clearance_itself_after_a_red_stop(world):
    """The builder's session ends on its sixth red stop: run_seat.py stops the slice and tries self-clear at once; with
    cause (a) it is cleared and logged, with no line from anyone; with neither cause it stays stopped for the owner."""
    from test_seat_failure import builder_done, run_seat
    w = world
    wt = a_slice_red_on_its_own(w)
    set_state(w, phase="building")  # the session that met the sixth red stop is the one run_seat.py launches
    p, _ = run_seat(w, "builder", [builder_done()])
    assert p.returncode == 0 and "STOPPED S1" in p.stdout and "cleared by the line (cause a)" in p.stdout, p.stdout
    assert state(w)["phase"] == "building" and [r["cause"] for r in clears(w)] == ["a"]
    red_six_times(w, wt)
    set_state(w, phase="building")
    p, _ = run_seat(w, "builder", [builder_done("b-2")])
    assert p.returncode == 1 and "not cleared by the line" in p.stdout, p.stdout
    assert state(w)["phase"] == "stopped" and len(clears(w)) == 1


def test_cause_a_needs_main_to_merge_cleanly(world):
    w = world
    wt = layout_slice(w)
    (wt / "README.md").write_text("the slice's\n")
    (wt / "accept.sh").write_text("exit 1\n")
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'feat: S1, red'", wt, w["env"])
    red_six_times(w, wt)
    commit_main(w, {"README.md": "main's\n"})
    before, heads = snapshot(w), (sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "does not merge into the branch cleanly", "README.md"), p.stdout + p.stderr
    unchanged(w, wt, before, heads)
