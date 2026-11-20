"""The resume step (resume.py): a stopped slice goes back to its builder only on the owner's written word, or, for the
conductor's own malformed command, within limits the code holds (the owner's rulings 3 and 4, 18 November 2026).

Each case runs resume.py as the conductor runs it: a subprocess in a throwaway repository shaped like this one, with the
slice started by slice_start.py and stopped as the line stops it (the Stop hook's six red stops, or the verifier's
findings at the rounds limit). The owner's word is a line in resume.tsv, which only the owner can write.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import time

import pytest

from test_gates import bash, guard, refused, sh, started, stop_gate, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
TODAY = time.strftime("%Y-%m-%d", time.gmtime())
RULINGS_COPY = "Claude outputs/slice-line/RULINGS.md"


def resume(w, slice_id, action, env=None):
    return sh([w["py"], str(w["lines"] / "resume.py"), slice_id, action], w["repo"], {**w["env"], **(env or {})},
              check=False)


def said_refused(p, *words):
    """resume.py's own refusal (never a crash), naming why."""
    out = p.stdout + p.stderr
    return (p.returncode == 1 and p.stderr.startswith("Refused: ") and "Traceback" not in out
            and all(w_ in p.stderr for w_ in words))


def owner_line(w, *lines):
    (w["repo"] / V062 / "resume.tsv").write_text("".join(f"{ln}\n" for ln in lines))


def state(w, slice_id="S1"):
    return json.loads((w["data"] / f"records/{slice_id}/state.json").read_text())


def set_state(w, slice_id="S1", **kw):
    p = w["data"] / f"records/{slice_id}/state.json"
    st = json.loads(p.read_text())
    st.update(kw)
    p.write_text(json.dumps(st))


def snapshot(w):
    """Every record file and the owner's three yaml files, byte for byte."""
    files = sorted(p for p in (w["data"] / "records").rglob("*") if p.is_file())
    snap = {str(p): p.read_bytes() for p in files}
    for f in ("dial.yaml", "accounts.yaml", "live_step.yaml"):
        snap[f] = (w["repo"] / V062 / f).read_bytes()
    return snap


def yamls(w):
    return {f: hashlib.sha256((w["repo"] / V062 / f).read_bytes()).hexdigest()
            for f in ("dial.yaml", "accounts.yaml", "live_step.yaml")}


def with_rulings(w, text="# Rulings\n\nThe first ruling.\n"):
    (w["repo"] / V062 / "RULINGS.md").write_text(text)
    sh(["git", "add", f"{V062}/RULINGS.md"], w["repo"], w["env"])
    sh(["git", "commit", "-qm", "docs(process): rulings\n\nSlice-Records: yes"], w["repo"], w["env"])


def at_limit(w):
    """S1 started and stopped by its verifier's findings at its rounds limit, as run_seat.py stops it."""
    with_rulings(w)
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    set_state(w, round=st["rounds_limit"], phase="stopped",
              note="findings after 2 round(s) (first: x): accept a narrower slice, or allow another round?")
    return wt


def red_stopped(w):
    """S1 started and stopped by the Stop hook after six red stops."""
    with_rulings(w)
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    (wt / "accept.sh").write_text("echo 'FAILED tests/test_a.py::test_x - AssertionError: no'; exit 1\n")
    sh("git add accept.sh && git commit -qm 'test: red'", wt, w["env"])
    for _ in range(6):
        stop_gate(w, wt)
    assert (w["data"] / "records/S1/red_stop.json").exists()
    set_state(w, phase="stopped", note="the builder could not get the checks green in 6 tries: narrow it?")
    return wt


def changes(w):
    f = w["data"] / "owner-changes.tsv"
    return [ln.split("\t") for ln in f.read_text().splitlines()[1:]] if f.exists() else []


# ------------------------------------------------------------------ the owner's word, and only it


@pytest.mark.parametrize("line", [None, "S9\tadd-round\t@TODAY@", "S1\tclear-stop\t@TODAY@", "S1\tadd-round\t2020-01-01",
                                  "# S1\tadd-round\t@TODAY@", "S1 add-round"],
                         ids=["no-line", "another-slice", "another-action", "another-day", "a-comment", "no-day"])
def test_resume_refuses_without_the_owners_line_for_that_slice_action_and_day_and_changes_nothing(world, line):
    w = world
    wt = at_limit(w)
    if line is not None:
        owner_line(w, line.replace("@TODAY@", TODAY))
    before, head = snapshot(w), sh("git rev-parse HEAD", wt).stdout
    p = resume(w, "S1", "add-round")
    assert said_refused(p, "no line", "resume.tsv"), p.stdout + p.stderr
    assert snapshot(w) == before and sh("git rev-parse HEAD", wt).stdout == head
    assert not (wt / RULINGS_COPY).exists() and changes(w) == []


def test_resume_a_line_is_used_once_and_each_use_is_logged(world):
    w = world
    at_limit(w)
    owner_line(w, f"S1\tadd-round\t{TODAY}")
    p = resume(w, "S1", "add-round")
    assert p.returncode == 0, p.stdout + p.stderr
    log = changes(w)
    assert len(log) == 1 and log[0][1:3] == ["S1", "add-round"] and f"resume.tsv {TODAY}" in log[0][3], log
    set_state(w, phase="stopped", note="findings again: allow another round?")  # stopped at the new limit
    before = snapshot(w)
    p = resume(w, "S1", "add-round")
    assert said_refused(p, "already used"), p.stderr
    assert snapshot(w) == before and len(changes(w)) == 1
    owner_line(w, f"S1\tadd-round\t{TODAY}", f"S1\tadd-round\t{TODAY}")  # a second line: a second use
    assert resume(w, "S1", "add-round").returncode == 0 and len(changes(w)) == 2


def test_resume_add_round_gives_one_more_round_and_brings_the_rulings_without_a_commit(world):
    w = world
    wt = at_limit(w)
    st0 = state(w)
    head = sh("git rev-parse HEAD", wt).stdout
    owner_line(w, f"S1\tadd-round\t{TODAY}")
    keep = yamls(w)
    # main's rulings move on after the slice started; the worktree is a snapshot
    with_rulings(w, "# Rulings\n\nThe first ruling.\n\nA newer ruling, given since the slice started.\n")
    p = resume(w, "S1", "add-round")
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert (st["phase"], st["round"], st["rounds_limit"]) == ("building", st0["round"] + 1, st0["rounds_limit"] + 1)
    assert "note" not in st
    assert "A newer ruling" in (wt / RULINGS_COPY).read_text()
    assert sh("git rev-parse HEAD", wt).stdout == head                      # nothing committed on the slice's branch
    assert sh("git status --porcelain", wt).stdout.strip() == ""            # and git never sees the copy
    assert yamls(w) == keep


def test_resume_add_round_refuses_a_slice_not_stopped_at_its_rounds_limit(world):
    w = world
    red_stopped(w)  # stopped on red checks, not at the limit
    owner_line(w, f"S1\tadd-round\t{TODAY}")
    before = snapshot(w)
    p = resume(w, "S1", "add-round")
    assert said_refused(p, "rounds limit"), p.stderr
    assert snapshot(w) == before and changes(w) == []


def test_resume_clear_stop_returns_a_red_stopped_slice_to_building(world):
    w = world
    wt = red_stopped(w)
    owner_line(w, f"S1\tclear-stop\t{TODAY}")
    keep = yamls(w)
    p = resume(w, "S1", "clear-stop")
    assert p.returncode == 0, p.stdout + p.stderr
    rec = w["data"] / "records/S1"
    assert not (rec / "red_stop.json").exists() and not (rec / "red_stops").exists()
    assert state(w)["phase"] == "building" and (wt / RULINGS_COPY).exists()
    assert yamls(w) == keep and changes(w)[0][2] == "clear-stop"


def test_resume_refreeze_commits_that_slices_frozen_columns_alone_and_keeps_the_history(world):
    w = world
    red_stopped(w)
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("sh accept.sh\ttrue", "sh accept.sh\ttrue && true"))
    owner_line(w, f"S1\trefreeze\t{TODAY}")
    keep = yamls(w)
    p = resume(w, "S1", "refreeze")
    assert p.returncode == 0, p.stdout + p.stderr
    msg = sh("git log -1 --format=%B main", w["repo"]).stdout
    assert "Slice-Records: yes" in msg
    assert sh("git show --name-only --format= main", w["repo"]).stdout.split() == [f"{V062}/slices.tsv"]
    frozen = json.loads((w["data"] / "records/S1/frozen.json").read_text())
    assert frozen["checks"] == "true && true" and frozen["history"][-1]["checks"] == "true"
    assert yamls(w) == keep


@pytest.mark.parametrize("change", ["another-row", "a-column-not-frozen", "nothing"])
def test_resume_refreeze_refuses_a_change_beyond_that_slices_frozen_columns(world, change):
    w = world
    red_stopped(w)
    tsv = w["repo"] / V062 / "slices.tsv"
    text = tsv.read_text()
    if change == "another-row":
        text = text.replace("sh accept.sh\ttrue", "sh accept.sh\ttrue && true").replace("sh accept2.sh\ttrue", "sh accept2.sh\tfalse")
    elif change == "a-column-not-frozen":
        text = text.replace("A test slice", "A wider slice").replace("sh accept.sh\ttrue", "sh accept.sh\ttrue && true")
    tsv.write_text(text)
    owner_line(w, f"S1\trefreeze\t{TODAY}")
    before, head = snapshot(w), sh("git rev-parse main", w["repo"]).stdout
    p = resume(w, "S1", "refreeze")
    assert said_refused(p), p.stdout + p.stderr
    assert snapshot(w) == before and sh("git rev-parse main", w["repo"]).stdout == head and changes(w) == []


def test_resume_refuses_while_a_merge_runs_or_the_worktree_has_uncommitted_changes(world):
    w = world
    wt = at_limit(w)
    owner_line(w, f"S1\tadd-round\t{TODAY}")
    before = snapshot(w)
    with (w["data"] / "merge.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        p = resume(w, "S1", "add-round")
    assert said_refused(p, "another merge is running"), p.stderr
    (wt / "half-done.txt").write_text("an agent's work\n")
    p = resume(w, "S1", "add-round")
    assert said_refused(p, "uncommitted"), p.stderr
    assert snapshot(w) == before and changes(w) == []


# ------------------------------------------------------------------ a branch behind main in the records folder


def test_resume_merges_main_into_a_branch_whose_only_conflict_is_the_records_folder(world):
    """BL6, 18 November 2026: a copy of main's RULINGS.md committed on the branch; main's changed after; the merge refused."""
    w = world
    wt = at_limit(w)
    (wt / V062 / "RULINGS.md").write_text("# Rulings\n\nThe branch's copy.\n")
    sh(f"git add {V062}/RULINGS.md && git commit -qm 'docs: a copy of the rulings'", wt, w["env"])
    (wt / "feature.txt").write_text("done\n")
    sh("git add feature.txt && git commit -qm 'feat: S1'", wt, w["env"])
    with_rulings(w, "# Rulings\n\nMain's newer text.\n")
    owner_line(w, f"S1\tadd-round\t{TODAY}")
    p = resume(w, "S1", "add-round")
    assert p.returncode == 0, p.stdout + p.stderr
    assert (wt / V062 / "RULINGS.md").read_text() == "# Rulings\n\nMain's newer text.\n"
    assert (wt / "feature.txt").exists() and sh("git status --porcelain", wt).stdout.strip() == ""
    assert sh("git rev-list --parents -1 HEAD", wt).stdout.count(" ") == 2   # a merge commit
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    rec = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())
    assert rec["verdict"] == "findings" and "change nothing else" in rec["findings"][0]["what"].lower()
    assert state(w)["phase"] == "building"


def test_resume_leaves_a_conflict_outside_the_records_folder_to_the_builder(world):
    w = world
    wt = at_limit(w)
    (wt / "README.md").write_text("the branch's\n")
    sh("git commit -qam 'docs: readme'", wt, w["env"])
    (w["repo"] / "README.md").write_text("main's\n")
    sh("git commit -qam 'docs: readme on main' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    owner_line(w, f"S1\tadd-round\t{TODAY}")
    head = sh("git rev-parse HEAD", wt).stdout
    p = resume(w, "S1", "add-round")
    assert p.returncode == 0, p.stdout + p.stderr
    assert sh("git rev-parse HEAD", wt).stdout == head and "README.md" in p.stdout
    assert sh("git status --porcelain", wt).stdout.strip() == ""


# ------------------------------------------------------------------ the guard


def test_resume_tsv_is_refused_to_every_seat(world):
    w = world
    f = w["repo"] / V062 / "resume.tsv"
    for seat in (None, "conductor", "builder", "verifier", "scout"):
        kw = {"seat": seat} if seat else {}
        if seat == "builder":
            kw["wt"] = w["repo"]
        assert refused(guard(w, "Write", {"file_path": str(f), "content": f"S1\tadd-round\t{TODAY}\n"}, **kw)), seat
        assert refused(guard(w, "Edit", {"file_path": str(f), "old_string": "a", "new_string": "b"}, **kw)), seat
        assert refused(bash(w, f"printf 'S1\\tadd-round\\t{TODAY}\\n' >> {V062}/resume.tsv", **kw)), seat


def test_the_conductor_runs_resume_whole_and_no_other_seat_runs_it(world):
    w = world
    cmd = f"{w['py']} OspreyFlow_Build/scripts/slice_line/resume.py S1 add-round"
    assert bash(w, cmd, seat="conductor").returncode == 0
    assert refused(bash(w, cmd + " && git commit -qm x", seat="conductor"))  # chained: no longer the script alone
    wt = w["tmp"] / "wt" / "slice-S1"
    sh(["git", "worktree", "add", "-q", "-b", "lane/slice-S1", str(wt), "main"], w["repo"], w["env"])
    for seat in ("builder", "verifier", "scout"):
        assert refused(bash(w, cmd, seat=seat, wt=wt, cwd=wt)), seat


# ------------------------------------------------------------------ correct-command: the conductor's own malformed command


def malformed(w, checks):
    """S1 started on a command that was malformed (as BL6 and AD2 were, before the dry run at start existed), then
    stopped by the Stop hook after six red stops on it."""
    with_rulings(w)
    (w["repo"] / "tests").mkdir(exist_ok=True)
    (w["repo"] / "tests/test_s1.py").write_text("def test_s1():\n    assert True\n")
    (w["repo"] / "tools").mkdir(exist_ok=True)
    (w["repo"] / "tools/Makefile").write_text("all:\n\t@echo built\n")
    sh("git add tests tools && git commit -qm 'test: s1' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("sh accept.sh\ttrue", f"sh accept.sh\t{checks}"))
    sh(f"git add {V062}/slices.tsv && git commit -qm 'docs: S1 checks' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    fz = w["data"] / "records/S1/frozen.json"
    frozen = json.loads(fz.read_text())
    frozen["checks"] = checks
    fz.write_text(json.dumps(frozen))
    (wt / "accept.sh").write_text("test -f feature.txt\n")
    (wt / "feature.txt").write_text("done\n")
    sh("git add accept.sh feature.txt && git commit -qm 'feat: S1'", wt, w["env"])
    for _ in range(6):
        stop_gate(w, wt)
    assert (w["data"] / "records/S1/red_stop.json").exists()
    set_state(w, phase="stopped", note="the builder could not get the checks green in 6 tries")
    return wt


def corrected(w, old, new):
    tsv = w["repo"] / V062 / "slices.tsv"
    assert f"\t{old}\n" in tsv.read_text()
    tsv.write_text(tsv.read_text().replace(f"\t{old}\n", f"\t{new}\n"))


PYTEST = "{py} -m pytest -q -p no:cacheprovider tests/test_s1.py"


def test_correct_command_resumes_a_slice_stopped_only_by_its_own_malformed_make_path(world):
    w = world
    py = PYTEST.format(py=w["py"])
    old, new = f"{py} && make -C tool all", f"{py} && make -C tools all"
    wt = malformed(w, old)
    corrected(w, old, new)
    keep = yamls(w)
    p = resume(w, "S1", "correct-command")  # no line in resume.tsv: the conductor's standing authority (ruling 3)
    assert p.returncode == 0, p.stdout + p.stderr
    frozen = json.loads((w["data"] / "records/S1/frozen.json").read_text())
    assert frozen["checks"] == new and frozen["history"][-1]["checks"] == old
    assert "Slice-Records: yes" in sh("git log -1 --format=%B main", w["repo"]).stdout
    assert not (w["data"] / "records/S1/red_stop.json").exists() and state(w)["phase"] == "building"
    log = changes(w)
    assert log[-1][2] == "correct-command" and old in log[-1][3] and new in log[-1][3]
    board = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    assert "command corrected" in board.stdout and new in board.stdout
    assert yamls(w) == keep and (wt / RULINGS_COPY).exists()


def test_correct_command_resumes_a_slice_stopped_on_a_missing_port_slot(world):
    w = world
    slot_check = "test -n \"$OSPREY_PORTS_SLOT\" || { echo 'Error: OSPREY_PORTS_SLOT is not set for a linked worktree'; exit 1; }"
    py = PYTEST.format(py=w["py"])
    old = f"{py} && export OSPREY_PORTS_SLOT= && {slot_check}"
    new = f"{py} && export OSPREY_PORTS_SLOT=99 && {slot_check}"
    malformed(w, old)
    corrected(w, old, new)
    p = resume(w, "S1", "correct-command")
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize("new", [
    "{py} tests/test_s2.py && make -C tools all",                      # swaps a test file
    "{py} tests/test_s1.py tests/test_s2.py && make -C tools all",      # adds one
    "{py} && make -C tools all",                                         # drops one (no file: the whole folder)
    "{py} tests/test_s1.py && make -C tools all || true",               # changes what the check tests
    "{py} tests/test_s1.py -k s1 && make -C tools all",                 # so does this, though it passes
], ids=["swaps", "adds", "drops", "or-true", "dash-k"])
def test_correct_command_refuses_a_corrected_command_that_changes_what_is_tested(world, new):
    w = world
    base = f"{w['py']} -m pytest -q -p no:cacheprovider"
    old = f"{base} tests/test_s1.py && make -C tool all"
    (w["repo"] / "tests").mkdir(exist_ok=True)
    (w["repo"] / "tests/test_s2.py").write_text("def test_s2():\n    assert True\n")
    sh("git add tests && git commit -qm 'test: s2' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    malformed(w, old)
    corrected(w, old, new.format(py=base))
    before, head = snapshot(w), sh("git rev-parse main", w["repo"]).stdout
    p = resume(w, "S1", "correct-command")
    assert said_refused(p), p.stdout + p.stderr
    assert snapshot(w) == before and sh("git rev-parse main", w["repo"]).stdout == head and changes(w) == []


def test_correct_command_refuses_a_stop_on_a_genuine_failing_assertion(world):
    w = world
    red_stopped(w)  # its last red is "FAILED ... AssertionError": not the conductor's command
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("sh accept.sh\ttrue", "sh accept.sh\ttrue && true"))
    before = snapshot(w)
    p = resume(w, "S1", "correct-command")
    assert said_refused(p, "malformed"), p.stderr
    assert snapshot(w) == before and changes(w) == []


def test_correct_command_refuses_a_correction_not_proved_on_main(world):
    w = world
    py = PYTEST.format(py=w["py"])
    old, new = f"{py} && make -C tool all", f"{py} && make -C tooling all"   # still a folder that does not exist
    malformed(w, old)
    corrected(w, old, new)
    before = snapshot(w)
    p = resume(w, "S1", "correct-command")
    assert said_refused(p, "on main"), p.stderr
    assert snapshot(w) == before and changes(w) == []
