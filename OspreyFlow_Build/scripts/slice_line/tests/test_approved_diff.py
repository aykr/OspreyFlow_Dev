"""The owner's approved decision-record diffs (LINE_FIXES_5_BRIEF.md, 10; the owner's word of 21 November 2026).

The owner approves a diff in chat as `approved: <name> <hash8>` (hash8: the first 8 characters of the diff file's
SHA-256). The conductor records it with `merge_slice.py approve-diff <name> <hash8>` (refused unless the hash8 is the
file's now) and applies it with `merge_slice.py apply-approved <name>`, which refuses unless the recorded approval's
SHA-256 is the file's now, every file it touches is one of the five allowed (never the Makefile, a workflow,
harness/signatures.py or the owner's lanes files; a rename or mode change never), it applies to main's tip, and the
decision checks are green on the result. It then commits with "approved by the owner, <date>", `Slice-Records: yes` and
`Owner-Approved-Diff: <name>`, appends name, hash8, commit and date to approved/applied.tsv (which the board prints for
the top of each report) and pushes. The guard still refuses the conductor's own `git apply` or redirect into the spec.

The decision checks here are stand-ins at their real call site (`python -m tools.<check>` from the tree's
OspreyFlow_Core with the tree's OspreyFlow_Build on PYTHONPATH); the reservation check's is red on a "BROKEN" line.
"""
from __future__ import annotations

import hashlib
import json

import pytest

import time

from test_gates import bash, refused, sh, world  # noqa: F401  (world is a fixture)

TODAY = time.strftime("%Y-%m-%d", time.gmtime())

V062 = "OspreyFlow_Build/process/lanes/v062"
PROPOSALS = f"{V062}/slice-line/proposals"
DECISIONS = "OspreyFlow_Build/spec/06_DECISIONS.md"
RESERVATIONS = "OspreyFlow_Build/spec/ADR_RESERVATIONS.md"
CHECK = '''import sys
from pathlib import Path
text = (Path(__file__).resolve().parents[1] / "spec/ADR_RESERVATIONS.md").read_text()
if "BROKEN" in text:
    print("ADR-999 is reserved twice")
    sys.exit(1)
'''
GREEN = "import sys\nsys.exit(0)\n"


@pytest.fixture
def spec(world):
    w = world
    files = {DECISIONS: "# Decisions\n\n## ADR-001\n\nThe first.\n", RESERVATIONS: "| ADR | slice |\n| 1 | x |\n",
             "OspreyFlow_Build/spec/design/DESIGN.md": "# Design\n", "OspreyFlow_Core/DESIGN.md": "# Design\n",
             "OspreyFlow_Build/process/CLAUDE.md": "# Rules\n", "OspreyFlow_Core/harness/signatures.py": "KEYS = ()\n",
             "OspreyFlow_Build/tools/__init__.py": "", "OspreyFlow_Build/tools/adr_reservations_check.py": CHECK,
             "OspreyFlow_Build/tools/doc_citations_check.py": GREEN,
             "OspreyFlow_Build/tools/decision_log_publication_check.py": GREEN}
    for rel, text in files.items():
        (w["repo"] / rel).parent.mkdir(parents=True, exist_ok=True)
        (w["repo"] / rel).write_text(text)
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: spec' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    sh("git push -q origin main", w["repo"], w["env"])
    return w


def make_diff(w, name, edits: dict) -> str:
    """The conductor's proposed diff of these edits against main, committed in the proposals folder; its hash8."""
    r = w["repo"]
    for rel, text in edits.items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(text)
    sh("git add -N . ':!OspreyFlow_Core/osprey.yaml'", r, w["env"])
    d = sh(["git", "diff", "--", *edits], r, w["env"]).stdout
    sh(["git", "reset", "-q", "--", *edits], r, w["env"])
    for rel in edits:
        if sh(["git", "cat-file", "-e", f"HEAD:{rel}"], r, check=False).returncode == 0:
            sh(["git", "checkout", "-q", "--", rel], r, w["env"])
        else:
            (r / rel).unlink()
    f = r / PROPOSALS / f"{name}.diff"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(d)
    sh(f"git add {PROPOSALS}/{name}.diff && git commit -qm 'docs: {name}' --trailer 'Slice-Records: yes'", r, w["env"])
    return hashlib.sha256(f.read_bytes()).hexdigest()[:8]


def ms(w, *args):
    return sh([w["py"], str(w["lines"] / "merge_slice.py"), *args], w["repo"], w["env"], check=False)


def heads(w):
    r = w["repo"]
    return (sh("git rev-parse HEAD", r).stdout, sh("git diff --cached --name-only", r).stdout,
            sh("git status --porcelain --untracked-files=no", r).stdout, (r / DECISIONS).read_text())


def nothing_changed(w, before):
    assert heads(w) == before
    assert not (w["repo"] / f"{V062}/approved/applied.tsv").exists()


def approved(w, name, edits):
    h = make_diff(w, name, edits)
    p = ms(w, "approve-diff", name, h)
    assert p.returncode == 0, p.stdout + p.stderr
    return h


def test_the_happy_path_commits_with_the_trailer_lists_it_and_pushes(spec):
    w = spec
    h = approved(w, "ADR002", {DECISIONS: "# Decisions\n\n## ADR-001\n\nThe first.\n\n## ADR-002\n\nThe second.\n"})
    rec = json.loads((w["repo"] / f"{V062}/approved/ADR002.json").read_text())
    assert rec["hash8"] == h and rec["sha256"].startswith(h)
    p = ms(w, "apply-approved", "ADR002")
    assert p.returncode == 0 and "Applied the owner's approved ADR002" in p.stdout, p.stdout + p.stderr
    r = w["repo"]
    applied = sh("git rev-parse HEAD~1", r).stdout.strip()
    msg = sh(["git", "log", "-1", "--format=%B", applied], r).stdout
    assert f"approved by the owner, {TODAY}" in msg and "Owner-Approved-Diff: ADR002" in msg and "Slice-Records: yes" in msg
    assert h in msg
    assert sh(["git", "show", "--name-only", "--format=", applied], r).stdout.split() == [DECISIONS]
    assert "ADR-002" in (r / DECISIONS).read_text()
    lines = (r / f"{V062}/approved/applied.tsv").read_text().splitlines()
    assert lines[1].split("\t") == [TODAY, "ADR002", h, applied], lines
    assert sh("git ls-remote origin refs/heads/main", r).stdout.split()[0] == sh("git rev-parse HEAD", r).stdout.strip()
    board = sh([w["py"], str(w["lines"] / "board.py")], r, w["env"]).stdout
    assert f"owner-approved diff applied: ADR002 {h} commit {applied[:10]}" in board.splitlines()[1], board


def test_a_diff_changed_after_approval_is_refused(spec):
    w = spec
    approved(w, "ADR002", {DECISIONS: "# Decisions\n\nchanged\n"})
    f = w["repo"] / PROPOSALS / "ADR002.diff"
    f.write_text(f.read_text().replace("+changed", "+changed again"))
    sh(f"git commit -qam 'docs: the diff again' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    before = heads(w)
    p = ms(w, "apply-approved", "ADR002")
    assert p.returncode == 1 and "has changed since the owner approved it" in p.stderr and "ask him again" in p.stderr
    nothing_changed(w, before)


@pytest.mark.parametrize("rel", ["OspreyFlow_Core/Makefile", ".github/workflows/ci.yml", ".github/workflows/release.yml",
                                 "OspreyFlow_Core/harness/signatures.py", f"{V062}/dial.yaml", f"{V062}/resume.tsv",
                                 "OspreyFlow_Build/spec/00_ARCHITECTURE.md"],
                         ids=["makefile", "ci-yml", "release-yml", "signatures", "dial", "resume-tsv", "another-spec-file"])
def test_a_diff_touching_a_file_outside_the_five_is_refused(spec, rel):
    w = spec
    approved(w, "X", {rel: "changed\n"})
    before = heads(w)
    p = ms(w, "apply-approved", "X")
    assert p.returncode == 1 and f"the diff touches {rel}" in p.stderr and "Nothing changed" in p.stderr, p.stderr
    nothing_changed(w, before)


def test_one_allowed_and_one_excluded_file_is_refused_whole(spec):
    w = spec
    approved(w, "X", {DECISIONS: "# Decisions\n\nnew\n", "OspreyFlow_Core/Makefile": "all:\n\tfalse\n"})
    before = heads(w)
    p = ms(w, "apply-approved", "X")
    assert p.returncode == 1 and "The whole diff is refused" in p.stderr and "never the Makefile" in p.stderr, p.stderr
    nothing_changed(w, before)


def test_a_diff_that_does_not_apply_is_refused_with_nothing_staged(spec):
    w = spec
    approved(w, "X", {DECISIONS: "# Decisions\n\nnew\n"})
    (w["repo"] / DECISIONS).write_text("# Decisions, rewritten since\n")
    sh(f"git commit -qam 'docs: decisions' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    before = heads(w)
    p = ms(w, "apply-approved", "X")
    assert p.returncode == 1 and "does not apply to main" in p.stderr, p.stderr
    nothing_changed(w, before)


def test_a_diff_that_breaks_the_reservation_check_is_refused_with_nothing_committed(spec):
    w = spec
    approved(w, "X", {RESERVATIONS: "| ADR | slice |\n| 1 | x |\nBROKEN\n"})
    before = heads(w)
    p = ms(w, "apply-approved", "X")
    assert p.returncode == 1 and "tools.adr_reservations_check is red" in p.stderr and "ADR-999" in p.stderr, p.stderr
    nothing_changed(w, before)


def test_an_approval_for_another_name_is_refused(spec):
    w = spec
    approved(w, "Y", {DECISIONS: "# Decisions\n\ny\n"})
    make_diff(w, "X", {DECISIONS: "# Decisions\n\nx\n"})
    before = heads(w)
    p = ms(w, "apply-approved", "X")
    assert p.returncode == 1 and "no approval of X is recorded" in p.stderr, p.stderr
    nothing_changed(w, before)


def test_a_stale_approval_whose_diff_was_deleted_is_refused(spec):
    w = spec
    approved(w, "X", {DECISIONS: "# Decisions\n\nx\n"})
    sh(f"git rm -q {PROPOSALS}/X.diff && git commit -qm 'docs: withdrawn' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    before = heads(w)
    p = ms(w, "apply-approved", "X")
    assert p.returncode == 1 and "is not there any more: the approval is stale" in p.stderr, p.stderr
    nothing_changed(w, before)


@pytest.mark.parametrize("given", ["wrong", "name-only"])
def test_approve_diff_takes_the_name_and_its_hash8_and_refuses_a_mismatch(spec, given):
    w = spec
    h = make_diff(w, "X", {DECISIONS: "# Decisions\n\nx\n"})
    args = ["approve-diff", "X"] + (["0" * 8 if h != "0" * 8 else "1" * 8] if given == "wrong" else [])
    p = ms(w, *args)
    assert p.returncode != 0 and not (w["repo"] / f"{V062}/approved/X.json").exists(), p.stdout + p.stderr
    if given == "wrong":
        assert "is not X.diff's" in p.stderr and "Ask him again" in p.stderr, p.stderr


def test_the_push_check_accepts_the_new_trailer_and_nothing_else_new(spec):
    w = spec
    r = w["repo"]
    (r / DECISIONS).write_text("# Decisions\n\npushed\n")
    sh(f"git commit -qam 'docs: approved' --trailer 'Owner-Approved-Diff: X'", r, w["env"])
    p = sh([str(w["lines"] / "push_main.sh")], r, w["env"], check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    (r / DECISIONS).write_text("# Decisions\n\nagain\n")
    sh(f"git commit -qam 'docs: approved' --trailer 'Owner-Approved: X'", r, w["env"])
    p = sh([str(w["lines"] / "push_main.sh")], r, w["env"], check=False)
    assert p.returncode == 2 and "not written by the merge script" in p.stdout, p.stdout + p.stderr


@pytest.mark.parametrize("cmd", [f"git apply {PROPOSALS}/X.diff", f"echo x >> {DECISIONS}",
                                 f"git apply {PROPOSALS}/X.diff && git commit -qam x", f"patch -p1 < {PROPOSALS}/X.diff",
                                 f"git am {PROPOSALS}/X.diff", f"git -C . apply --index {PROPOSALS}/X.diff"],
                         ids=["git-apply", "redirect", "apply-and-commit", "patch", "git-am", "apply-index"])
def test_the_guard_still_refuses_the_conductors_own_writes_into_the_spec(spec, cmd):
    p = bash(spec, cmd, seat="conductor")
    assert refused(p), (cmd, p.stderr)


def test_the_guard_lets_the_conductor_run_the_two_modes(spec):
    for cmd in ("python3 OspreyFlow_Build/scripts/slice_line/merge_slice.py approve-diff X 0123abcd",
                "python3 OspreyFlow_Build/scripts/slice_line/merge_slice.py apply-approved X"):
        p = bash(spec, cmd, seat="conductor")
        assert p.returncode == 0, (cmd, p.stderr)


def test_the_conductor_may_still_look_at_a_diff(spec):
    for cmd in (f"git apply --check {PROPOSALS}/X.diff", f"git apply --stat {PROPOSALS}/X.diff"):
        p = bash(spec, cmd, seat="conductor")
        assert p.returncode == 0, (cmd, p.stderr)
