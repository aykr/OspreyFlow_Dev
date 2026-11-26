"""P3, the owner's paperwork list, item 3: the conductor may apply a proved hand-back of the line-fix session that
touches no hook, guard, merge gate code or protected file (`merge_slice.py apply-handback <NN>`).

A hand-back is the line-fix session's apply_<NN>.sh in ~/dev/line-fixes-5/OUT, its patches in patches/ (each .patch
with the sha256 the script holds, and its .msg naming its red file and its planted faults' file, which ends "planted
faults not caught: 0"). The conductor applies it only when every file it touches is the board, the line's tests, the
early warning's tests or the line's README; anything else is the owner's, refused in words with the reason. It applies
under the merge lock, in a tree of main's tip, runs the line's suite and the early warning's there, and only then
fast-forwards main, lists the hand-back in handbacks/applied.tsv and pushes. The guard refuses the conductor's (and a
builder's) writes into the line-fix session's folder, so a hand-back is always that session's own.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import time

import pytest

from test_gates import SRC, bash, refused, sh, world  # noqa: F401  (world is a fixture)

sys.path.insert(0, str(SRC))

V062 = "OspreyFlow_Build/process/lanes/v062"
LINE = "OspreyFlow_Build/scripts/slice_line"
APPLIED = f"{V062}/slice-line/handbacks/applied.tsv"


def out(w):
    return w["home"] / "dev" / "line-fixes-5" / "OUT"


def handback(w, nn, edits: dict, after="", plants="planted faults not caught: 0\n", proofs=True, name=None,
             sha=None) -> str:
    """The line-fix session's hand-back <nn> of these edits against main, as it hands one back: its patch, .msg, red
    file, planted faults' file and apply_<nn>.sh (PATCHES, SHA256 and, with `after`, AFTER). Its subject."""
    r, o = w["repo"], out(w)
    name = name or f"{nn}-x-hand-back"
    for rel, text in edits.items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(text)
    sh("git add -N .", r, w["env"])
    d = sh(["git", "diff", "--", *edits], r, w["env"]).stdout
    sh(["git", "reset", "-q", "--", *edits], r, w["env"])
    for rel in edits:
        if sh(["git", "cat-file", "-e", f"HEAD:{rel}"], r, check=False).returncode == 0:
            sh(["git", "checkout", "-q", "--", rel], r, w["env"])
        else:
            (r / rel).unlink()
    for sub in ("patches", "red", "green"):
        (o / sub).mkdir(parents=True, exist_ok=True)
    (o / "patches" / f"{name}.patch").write_text(d)
    subject = f"fix(slice-line): hand-back {nn}, {name}"
    proof = f"Red first: red/{nn}.txt. Planted faults: green/{nn}-plants.txt.\n" if proofs else ""
    (o / "patches" / f"{name}.msg").write_text(f"{subject}\n\nWhat it does.\n\n{proof}")
    (o / "red" / f"{nn}.txt").write_text("FAILED test_x\n")
    (o / "green" / f"{nn}-plants.txt").write_text("RED  board.py -> test_x\n" + plants)
    digest = sha or hashlib.sha256((o / "patches" / f"{name}.patch").read_bytes()).hexdigest()
    (o / f"apply_{nn}.sh").write_text(
        "#!/usr/bin/env bash\nset -uo pipefail\n"
        f'PATCHES=("{name}")\nSHA256=("{digest}")\n' + (f'AFTER="{after}"\n' if after else "") + "echo the owner's\n")
    return subject


def ms(w, *args, **env):
    return sh([w["py"], str(w["lines"] / "merge_slice.py"), *args], w["repo"],
              {**w["env"], **{k: str(v) for k, v in env.items()}}, check=False)


def head(w, ref="HEAD", where=None):
    return sh(["git", "rev-parse", ref], where or w["repo"], w["env"]).stdout.strip()


def untouched(w, before):
    """Nothing landed: main where it was, nothing staged, no list, no tree of the hand-back's left."""
    r = w["repo"]
    assert head(w) == before
    assert sh("git status --porcelain --untracked-files=no -- . ':!OspreyFlow_Core/osprey.yaml'", r,
              w["env"]).stdout.strip() == ""                               # the owner's local osprey.yaml aside
    assert not (r / APPLIED).exists()
    assert "handback" not in sh("git worktree list", r, w["env"]).stdout


BOARD_LINE = "\n# hand-back: the board says it\n"


def board(w):
    return (w["lines"] / "board.py").read_text()


# ------------------------------------------------------------------ the conductor's: applied, tested, listed, pushed


def test_a_proved_hand_back_to_the_board_and_the_tests_is_applied_tested_listed_and_pushed(world, tmp_path):
    w = world
    subject = handback(w, "61", {f"{LINE}/board.py": board(w) + BOARD_LINE,
                                 f"{LINE}/tests/test_new.py": "def test_new():\n    pass\n",
                                 f"{V062}/slice-line/README.md": "# The line\n\nA rule.\n"})
    before = head(w)
    seen = tmp_path / "seen"
    p = ms(w, "apply-handback", "61", TEST_HANDBACK_SEES=seen)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "Applied hand-back 61" in p.stdout
    assert BOARD_LINE.strip() in seen.read_text()                         # the suites ran on the hand-back's tree
    r = w["repo"]
    log = sh(["git", "log", "--format=%s%n%b%x00", f"{before}..HEAD"], r, w["env"]).stdout
    assert subject in log and "Line-Fix-Hand-Back: 61 (61-x-hand-back, sha256 " in log
    assert BOARD_LINE.strip() in board(w)
    row = (r / APPLIED).read_text().splitlines()
    assert row[0] == "date\thand-back\tpatches\tcommit" and row[1].split("\t")[1] == "61"
    applied = row[1].split("\t")[3]
    assert sh(["git", "log", "-1", "--format=%s", applied], r, w["env"]).stdout.strip() == subject
    last = sh(["git", "log", "-1", "--format=%s%n%b"], r, w["env"]).stdout
    assert "hand-back 61 applied by the conductor" in last and "Slice-Records: yes" in last
    assert head(w, "main", w["origin"]) == head(w)                        # pushed
    assert "handback" not in sh("git worktree list", r, w["env"]).stdout


# ------------------------------------------------------------------ the owner's: refused in words, nothing landed


@pytest.mark.parametrize("rel,why", [
    (f"{LINE}/guard.py", "a hook"),
    (f"{LINE}/stop_check.py", "a hook"),
    (f"{LINE}/install.sh", "a hook"),
    (f"{LINE}/run_seat.py", "the guard"),
    (f"{LINE}/resume.py", "the guard on the conductor"),
    (f"{LINE}/merge_slice.py", "the merge's gate code"),
    (f"{LINE}/common.py", "the merge's gate code"),
    (f"{LINE}/server_gate.py", "the merge's gate code"),
    (f"{LINE}/early_warning.py", "the merge's gate code"),
    (f"{LINE}/demo_server/runner.py", "the merge's gate code"),
    (f"{LINE}/refreeze.py", "the owner's script"),
    ("OspreyFlow_Core/Makefile", "a protected file"),
    (".github/workflows/ci.yml", "a protected file"),
    (f"{V062}/resume.tsv", "the owner's file"),
    ("OspreyFlow_Core/app.py", "not on the conductor's list"),
], ids=lambda x: x.rsplit("/", 1)[-1] if "/" in x else x)
def test_a_hand_back_that_touches_anything_else_is_the_owners(world, rel, why):
    w = world
    f = w["repo"] / rel
    text = (f.read_text() if f.exists() else "") + "\n# changed\n"
    handback(w, "62", {f"{LINE}/board.py": board(w) + BOARD_LINE, rel: text})
    before = head(w)
    p = ms(w, "apply-handback", "62")
    assert p.returncode != 0 and f"{rel} ({why}" in p.stderr, p.stdout + p.stderr
    assert "It is the owner's: bash " in p.stderr and "apply_62.sh" in p.stderr
    untouched(w, before)


@pytest.mark.parametrize("fault,words", [
    ("sha", "is not the one handed back"),
    ("no-proofs", "names no red file"),
    ("plants-missed", "do not end 'planted faults not caught: 0'"),
    ("no-red-file", "is not in"),
])
def test_a_hand_back_not_the_one_handed_back_or_not_proved_is_refused(world, fault, words):
    w = world
    kw = {"sha": {"sha": "0" * 64}, "no-proofs": {"proofs": False},
          "plants-missed": {"plants": "STILL GREEN  board.py\nplanted faults not caught: 1\n"}}.get(fault, {})
    handback(w, "63", {f"{LINE}/board.py": board(w) + BOARD_LINE}, **kw)
    if fault == "no-red-file":
        (out(w) / "red" / "63.txt").unlink()
    before = head(w)
    p = ms(w, "apply-handback", "63")
    assert p.returncode != 0 and words in p.stderr, p.stdout + p.stderr
    untouched(w, before)


def test_a_hand_back_goes_on_main_only_after_the_one_before_it_and_only_once(world):
    w = world
    first = handback(w, "64", {f"{LINE}/board.py": board(w) + BOARD_LINE})
    handback(w, "65", {f"{LINE}/tests/test_65.py": "def test_65():\n    pass\n"}, after=first)
    before = head(w)
    p = ms(w, "apply-handback", "65")
    assert p.returncode != 0 and "goes on main after 'fix(slice-line): hand-back 64" in p.stderr, p.stdout + p.stderr
    untouched(w, before)
    assert ms(w, "apply-handback", "64").returncode == 0
    again = head(w)
    p = ms(w, "apply-handback", "64")
    assert p.returncode != 0 and "is on main already" in p.stderr, p.stdout + p.stderr
    assert head(w) == again
    p = ms(w, "apply-handback", "65")
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize("nn,words", [("../x", "is not a hand-back's number"), ("1", "is not a hand-back's number"),
                                      ("99", "there is no hand-back 99")])
def test_only_a_hand_back_in_the_line_fix_sessions_folder_by_its_number(world, nn, words):
    w = world
    before = head(w)
    p = ms(w, "apply-handback", nn)
    assert p.returncode != 0 and words in p.stderr, p.stdout + p.stderr
    assert head(w) == before


def test_the_hand_backs_folder_is_fixed_not_the_callers():
    import merge_slice
    from pathlib import Path
    assert merge_slice.HANDBACKS == Path.home() / "dev" / "line-fixes-5" / "OUT"
    text = (SRC / "merge_slice.py").read_text()
    assert text.count("HANDBACKS = Path.home() / \"dev\" / \"line-fixes-5\" / \"OUT\"\n") == 1


# ------------------------------------------------------------------ tested before it lands


def test_red_suites_land_nothing(world):
    w = world
    handback(w, "66", {f"{LINE}/board.py": board(w) + BOARD_LINE})
    before = head(w)
    p = ms(w, "apply-handback", "66", TEST_HANDBACK_SUITE=1, TEST_HANDBACK_SAID="== 1 failed, 8 passed in 1.00s ==")
    assert p.returncode != 0 and "its suites are red on the result (== 1 failed, 8 passed" in p.stderr, p.stderr
    untouched(w, before)
    assert BOARD_LINE.strip() not in board(w)


def test_stalled_suites_land_nothing(world):
    w = world
    handback(w, "67", {f"{LINE}/board.py": board(w) + BOARD_LINE})
    before = head(w)
    p = ms(w, "apply-handback", "67", TEST_HANDBACK_RUN="sleep 30", OSPREY_GATE_STALL_SECONDS=2)
    assert p.returncode != 0 and "suites stalled" in p.stderr, p.stdout + p.stderr
    untouched(w, before)


def test_main_moved_while_the_suites_ran_lands_nothing(world):
    w = world
    handback(w, "68", {f"{LINE}/board.py": board(w) + BOARD_LINE})
    r = w["repo"]
    p = ms(w, "apply-handback", "68",
           TEST_HANDBACK_RUN=f"git -C {r} commit -q --allow-empty -m 'a records commit' --trailer 'Slice-Records: yes'")
    assert p.returncode != 0 and "main moved while the hand-back was being tested" in p.stderr, p.stdout + p.stderr
    assert not (r / APPLIED).exists() and BOARD_LINE.strip() not in board(w)


def test_it_waits_for_a_running_merge_and_gives_up_after_its_wait(world):
    w = world
    handback(w, "69", {f"{LINE}/board.py": board(w) + BOARD_LINE})
    w["data"].mkdir(parents=True, exist_ok=True)
    holder = subprocess.Popen([sys.executable, "-c", (
        "import fcntl, sys, time; fh = open(sys.argv[1], 'w'); fcntl.flock(fh, fcntl.LOCK_EX); print('held', flush=True);"
        " time.sleep(float(sys.argv[2]))"), str(w["data"] / "merge.lock"), "4"], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        before = head(w)
        p = ms(w, "apply-handback", "69", "--wait", "0.02")
        assert p.returncode != 0 and "still running after" in p.stderr, p.stdout + p.stderr
        untouched(w, before)
        t0 = time.monotonic()
        p = ms(w, "apply-handback", "69", "--wait", "1")
        assert p.returncode == 0 and "waits for it" in p.stderr, p.stdout + p.stderr
        assert time.monotonic() - t0 > 1
    finally:
        holder.kill()


def test_the_real_suites_are_the_lines_and_the_early_warnings_through_their_own_run_sh(tmp_path):
    """merge_slice.handback_suites itself (the world has its stand-in): both run.sh in the tree, under run(); the first
    red is the answer."""
    import merge_slice
    tree = tmp_path / "tree"
    ran = tmp_path / "ran"
    for rel, code in (("tests/run.sh", 0), ("demo_server/tests/run.sh", 4)):
        f = tree / merge_slice.LINE_REL / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f'#!/usr/bin/env bash\necho "{rel} $SLICE_LINE_PY $EARLY_WARNING_PY" >> {ran}\nexit {code}\n')
    log = tmp_path / "suite.log"
    assert merge_slice.handback_suites(tree, log) == 4
    said = ran.read_text().splitlines()
    assert [s.split()[0] for s in said] == ["tests/run.sh", "demo_server/tests/run.sh"], said
    assert all(len(s.split()) == 3 for s in said), said                  # each given its python
    (tree / merge_slice.LINE_REL / "tests/run.sh").write_text("#!/usr/bin/env bash\nexit 2\n")
    ran.unlink()
    assert merge_slice.handback_suites(tree, log) == 2 and not ran.exists()  # red first: the second is not run


# ------------------------------------------------------------------ the guard: a hand-back is the line-fix session's


@pytest.mark.parametrize("cmd", [
    "cp /tmp/x.patch ~/dev/line-fixes-5/OUT/patches/61-x.patch",
    "echo 'PATCHES=(\"x\")' > /Users/o/dev/line-fixes-5/OUT/apply_61.sh",
    "sed -i '' s/a/b/ ~/dev/line-fixes-5/OUT/green/61-plants.txt",
    "python3 -c \"open('/Users/o/dev/line-fixes-5/OUT/red/61.txt','w').write('x')\"",
])
@pytest.mark.parametrize("seat", ["conductor", "builder"])
def test_the_guard_refuses_a_seats_write_into_the_line_fix_sessions_folder(world, cmd, seat):
    p = bash(world, cmd, seat=seat, wt=str(world["tmp"]))
    assert refused(p) and ("line-fix session's hand-backs" in p.stderr or seat == "builder"), p.stderr


def test_the_conductor_reads_a_hand_back_and_runs_the_verb(world):
    w = world
    assert not refused(bash(w, "cat ~/dev/line-fixes-5/OUT/COMMANDS_61.md", seat="conductor"))
    assert not refused(bash(w, f"python3 {w['repo']}/{LINE}/merge_slice.py apply-handback 61", seat="conductor"))
    p = bash(w, "cp /tmp/x.patch ~/dev/line-fixes-5/OUT/patches/61-x.patch", seat="conductor")
    assert refused(p) and "merge_slice.py apply-handback" in p.stderr, p.stderr
