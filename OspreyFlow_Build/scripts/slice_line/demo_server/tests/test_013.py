"""013 (the owner, 22 November 2026; conductor file 015: verify and server test together, server first, three at a
time). early_warning.py takes a slice whose builder's checks are green and whose verifier has not answered, and holds
that result for its tip; takes a slice in any phase whose newest verifier record is a pass for the branch's own tip
(the line-fix session's rule, as the owner ruled); tests a stack's slices above a red one again without it; and says
in plain words at the top of a note when a red is of the kind broken by what merged ahead. Against the local fake
server, with the stand-in gate."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time

from conftest import early, gate, note, out, sh, ssh_calls
from test_stack import slices
from test_trust import PASSED, makefiles

NOTES = "OspreyFlow_Build/process/lanes/v062/early_warning"


def rec(w, name):
    return w["data"] / "records" / name


def records(w, name, tip, phase, **st):
    r = rec(w, name)
    r.mkdir(parents=True, exist_ok=True)
    (r / "frozen.json").write_text(json.dumps({"branch": f"lane/slice-{name}", "acceptance": "true"}))
    (r / "state.json").write_text(json.dumps({"phase": phase, "tip": tip, **st}))


def green_tests(w, name, tip):
    (rec(w, name) / f"tests-{tip}.json").write_text(json.dumps({"slice": name, "commit": tip, "green": True}))


def verifier(w, name, tip, verdict="pass", gate_record=False):
    """A verifier's record for `tip` (or, with gate_record, the merge's own findings record), written now."""
    f = rec(w, name) / (f"verify-gate-{tip}.json" if gate_record else f"verify-{tip}.json")
    f.write_text(json.dumps({"slice": name, "commit": tip, "verdict": verdict, "passes": [], "findings": []}))
    t = time.time() + len(list(rec(w, name).glob("verify-*.json")))  # each later than the last, whatever the clock
    os.utime(f, (t, t))


def waiting_on_verifier(w):
    """S1 as the line leaves it when the builder's checks are green: phase verifying, the Stop hook's record."""
    records(w, "S1", w["tip"], "verifying")
    green_tests(w, "S1", w["tip"])


def run_id(text):
    return re.search(r"Run id: `([0-9a-f]{16})`", text).group(1)


def tree_of(text):
    return re.search(r"Candidate tree hash: `([0-9a-f]{40})`", text).group(1)


def standing(w, name="S1"):
    p = early(w, "standing", name)
    return p.returncode, json.loads(p.stdout.decode())


def move_tip(w, name="S1"):
    sh(["git", "switch", "-q", f"lane/slice-{name}"], w["repo"], w["env"])
    (w["repo"] / f"{name}-round.txt").write_text("the verifier's round\n")
    sh(f"git add {name}-round.txt && git commit -qm 'fix: the round'", w["repo"], w["env"])
    sh(["git", "switch", "-q", "main"], w["repo"], w["env"])
    return out(["git", "rev-parse", f"lane/slice-{name}"], w["repo"])


# ------------------------------------------------------------------ 1. tested before the verifier answers

def test_a_green_tip_waiting_on_its_verifier_is_tested_and_held(world):
    w = world
    waiting_on_verifier(w)
    p = early(w, "S1")
    assert p.returncode == 0, p.stdout + p.stderr
    text = note(w).read_text()
    assert text.splitlines()[0] == f"# Early warning: S1 at {w['tip'][:8]}: GREEN (tested, not yet verified)"
    assert f"<!-- held: tested, not yet verified, tip {w['tip']} -->" in text
    assert "counts for nothing until the verifier passes that exact commit" in text
    runs = [json.loads(x) for x in (w["data"] / "early-warning/runs.jsonl").read_text().splitlines()]
    assert runs[-1]["standing"] == "tested, not yet verified"


def test_while_it_runs_the_running_file_says_it_is_held(world):
    w = world
    waiting_on_verifier(w)
    gate(w, exit=0, sleep=4)
    proc = subprocess.Popen([w["py"], str(w["lines"] / "early_warning.py"), "S1"], cwd=w["repo"], env=w["env"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    f = w["data"] / "early-warning/running" / f"S1-{w['tip'][:8]}.json"
    for _ in range(100):
        if f.exists():
            break
        time.sleep(0.1)
    assert json.loads(f.read_text())["standing"] == "tested, not yet verified"
    proc.communicate(timeout=60)


def test_a_held_result_is_never_trusted_and_counts_once_the_verifier_passes_that_tip(world):
    w = world
    makefiles(w)
    waiting_on_verifier(w)
    gate(w, exit=0, checks=PASSED)
    assert early(w, "S1").returncode == 0
    text = note(w).read_text()
    jid, tree = run_id(text), tree_of(text)
    assert out(["git", "merge-tree", "--write-tree", "main", w["tip"]], w["repo"]).splitlines()[0] == tree
    p = early(w, "S1", "--trust", jid, "--tree", tree)
    said = json.loads(p.stdout.decode())
    assert p.returncode == 1 and said["trusted"] is False and "tested, not yet verified" in said["why"]
    verifier(w, "S1", w["tip"], "pass")  # the verifier passes exactly the tip tested
    code, st = standing(w)
    assert code == 0 and st["standing"] == "verified" and st["counts"] is True
    assert st["notes"]["now_verified"] == [note(w).name]
    assert "**Now verified.**" in note(w).read_text().splitlines()[2]
    p = early(w, "S1", "--trust", jid, "--tree", tree)
    assert p.returncode == 0 and json.loads(p.stdout.decode())["trusted"] is True


def test_when_the_verifiers_round_moves_the_tip_the_held_result_is_void_and_says_so(world):
    w = world
    makefiles(w)
    waiting_on_verifier(w)
    gate(w, exit=0, checks=PASSED)
    assert early(w, "S1").returncode == 0
    held = note(w)
    jid, tree = run_id(held.read_text()), tree_of(held.read_text())
    out(["git", "merge-tree", "--write-tree", "main", w["tip"]], w["repo"])
    verifier(w, "S1", w["tip"], "findings")
    new = move_tip(w)
    records(w, "S1", new, "verifying")
    green_tests(w, "S1", new)
    code, st = standing(w)
    assert code == 0 and st["standing"] == "tested, not yet verified" and st["tip"] == new, st
    assert st["notes"]["void"] == [held.name]
    line = held.read_text().splitlines()[2]
    assert line.startswith("**VOID.**") and w["tip"][:10] in line and new[:10] in line
    assert standing(w)[1]["notes"]["void"] == []  # said once
    verifier(w, "S1", new, "pass")
    p = early(w, "S1", "--trust", jid, "--tree", tree)  # the old tip's run, now the branch is verified elsewhere
    assert p.returncode == 1 and json.loads(p.stdout.decode())["trusted"] is False


def test_a_tip_whose_verifier_answered_with_findings_is_refused_and_nothing_is_sent(world):
    w = world
    waiting_on_verifier(w)
    verifier(w, "S1", w["tip"], "findings")
    p = early(w, "S1")
    assert p.returncode == 2 and b"answered" in p.stderr and ssh_calls(w) == []


def test_a_tip_without_the_builders_green_record_is_refused(world):
    w = world
    records(w, "S1", w["tip"], "verifying")
    p = early(w, "S1")
    assert p.returncode == 2 and b"not at verified" in p.stderr and ssh_calls(w) == []
    (rec(w, "S1") / f"tests-{w['tip']}.json").write_text(json.dumps({"commit": "0" * 40, "green": True}))
    assert early(w, "S1").returncode == 2  # a green record for another commit is none for this one


def test_a_building_slice_with_a_green_record_is_still_refused(world):
    w = world
    records(w, "S1", w["tip"], "building")
    green_tests(w, "S1", w["tip"])
    p = early(w, "S1")
    assert p.returncode == 2 and ssh_calls(w) == []


# ------------------------------------------------------------------ 2. any phase, newest verifier record a pass at the tip

def test_a_refused_slice_its_builder_has_not_touched_is_taken_as_verified(world):
    w = world
    records(w, "S1", w["tip"], "refused", refused_for="gate")
    verifier(w, "S1", w["tip"], "pass")
    verifier(w, "S1", w["tip"], "findings", gate_record=True)  # the merge's own record, written after: not a verifier's
    code, st = standing(w)
    assert code == 0 and st["standing"] == "verified" and "(phase refused)" in st["why"]
    p = early(w, "S1")
    assert p.returncode == 0 and "not yet verified" not in note(w).read_text()


def test_a_refused_slice_its_builder_has_touched_is_refused(world):
    w = world
    verifier_tip = w["tip"]
    records(w, "S1", verifier_tip, "refused", refused_for="gate")
    verifier(w, "S1", verifier_tip, "pass")
    move_tip(w)
    p = early(w, "S1")
    assert p.returncode == 2 and b"newest verifier record is not a pass" in p.stderr and ssh_calls(w) == []


def test_a_pass_that_is_not_the_newest_verifier_record_is_not_enough(world):
    w = world
    records(w, "S1", w["tip"], "refused")
    verifier(w, "S1", w["tip"], "pass")
    verifier(w, "S1", "1" * 40, "findings")  # a newer verifier record, for another commit
    p = early(w, "S1")
    assert p.returncode == 2 and ssh_calls(w) == []


def test_a_merged_slice_is_refused(world):
    w = world
    records(w, "S1", w["tip"], "merged")
    verifier(w, "S1", w["tip"], "pass")
    p = early(w, "S1")
    assert p.returncode == 2 and b"merged" in p.stderr and ssh_calls(w) == []



def accepted(w, name, tip, logged=True):
    """The owner's acceptance of the verifier's findings for `tip`, as resume.py accept leaves it: the verifier's
    findings record (a session that did not build it, whose transcript names the tip), accepted-<tip>.json holding
    those findings verbatim, and the use logged in owner-changes.tsv."""
    findings = [{"what": "a gap", "kind": "test_gap", "evidence": "a.py:1"}]
    transcript = rec(w, name) / "verifier-transcript.jsonl"
    transcript.write_text(f"the verifier read {tip}\n")
    f = rec(w, name) / f"verify-{tip}.json"
    f.write_text(json.dumps({"slice": name, "commit": tip, "verdict": "findings", "findings": findings,
                             "passes": [{"session": "v-1", "transcript": str(transcript)}]}))
    t = time.time() + len(list(rec(w, name).glob("verify-*.json")))
    os.utime(f, (t, t))
    (rec(w, name) / "sessions.json").write_text(json.dumps({"builder": ["b-1"], "verifier": ["v-1"]}))
    (rec(w, name) / f"accepted-{tip}.json").write_text(json.dumps({"slice": name, "tip": tip, "findings": findings,
                                                                    "by": "owner"}))
    if logged:
        (w["data"] / "owner-changes.tsv").write_text(f"at\tslice\taction\tdetail\nnow\t{name}\taccept\ttip {tip}\n")


def test_a_slice_the_owner_accepted_that_is_later_refused_is_taken(world):
    w = world
    records(w, "S1", w["tip"], "refused", refused_for="gate", accepted=True)
    accepted(w, "S1", w["tip"])
    code, st = standing(w)
    assert code == 0 and st["standing"] == "verified" and "owner accepted" in st["why"] and "(phase refused)" in st["why"]
    p = early(w, "S1")
    assert p.returncode == 0 and "not yet verified" not in note(w).read_text()


def test_an_acceptance_the_merge_would_not_take_is_no_acceptance(world):
    w = world
    records(w, "S1", w["tip"], "refused", refused_for="gate", accepted=True)
    accepted(w, "S1", w["tip"], logged=False)  # no use of the owner's word logged: resume.py never wrote it
    p = early(w, "S1")
    assert p.returncode == 2 and b"newest verifier record is not a pass" in p.stderr and ssh_calls(w) == []


def test_an_acceptance_behind_a_newer_verifier_record_is_not_enough(world):
    w = world
    records(w, "S1", w["tip"], "refused", accepted=True)
    accepted(w, "S1", w["tip"])
    verifier(w, "S1", "1" * 40, "findings")  # a newer verifier record, for another commit
    p = early(w, "S1")
    assert p.returncode == 2 and ssh_calls(w) == []


# ------------------------------------------------------------------ 3. a stack's slices above a red one, again without it

def three(w, *red_with):
    tips = {"S1": w["tip"], **slices(w, "S2", "S3")}
    for n in ("S2", "S3"):
        records(w, n, tips[n], "verified")
    gate(w, exit=0, red_with=list(red_with))
    return tips


def stacks_asked(w):
    return [c[c.index("stack") + 1:] if "stack" in c else ["run"] for c in ssh_calls(w) if "stack" in c or "run" in c]


def test_when_the_first_of_three_is_red_the_two_above_are_tested_again_without_it(world):
    w = world
    tips = three(w, "feature.txt")  # S1's own file: red wherever S1 is merged
    p = early(w, "S1", "S2", "S3")
    assert p.returncode == 1, p.stdout + p.stderr
    assert stacks_asked(w) == [["S1", "S2", "S3"], ["S2", "S3"]]
    d = w["repo"] / NOTES
    again2 = (d / f"S2-{tips['S2'][:8]}-without-S1.md").read_text()
    again3 = (d / f"S3-{tips['S3'][:8]}-after-S2-without-S1.md").read_text()
    first = re.search(r"The stack's run id: `([0-9a-f]{16})`", note(w).read_text()).group(1)
    for text in (again2, again3):
        assert ": GREEN" in text.splitlines()[0]
        assert f"**Tested again without S1**, which was red in stack `{first}`" in text
        assert re.search(r"The stack's run id: `([0-9a-f]{16})`", text).group(1) != first  # its own stack
    assert f"main + S2 `{tips['S2'][:10]}` + S3 `{tips['S3'][:10]}`" in again3
    assert ": RED" in (d / f"S2-{tips['S2'][:8]}-after-S1.md").read_text().splitlines()[0]  # the first stack's, kept


def test_when_the_middle_one_is_red_the_one_above_is_tested_on_the_one_below_without_it(world):
    w = world
    tips = three(w, "S2.txt")
    p = early(w, "S1", "S2", "S3")
    assert stacks_asked(w) == [["S1", "S2", "S3"], ["S1", "S3"]]
    text = (w["repo"] / NOTES / f"S3-{tips['S3'][:8]}-after-S1-without-S2.md").read_text()
    assert ": GREEN" in text.splitlines()[0] and "**Tested again without S2**" in text
    assert p.returncode == 1  # S2 stays red


def test_when_the_last_is_red_nothing_is_tested_again(world):
    w = world
    three(w, "S3.txt")
    assert early(w, "S1", "S2", "S3").returncode == 1
    assert stacks_asked(w) == [["S1", "S2", "S3"]]


def test_of_two_with_the_first_red_the_second_is_run_alone_without_it(world):
    w = world
    tips = {"S1": w["tip"], **slices(w, "S2")}
    records(w, "S2", tips["S2"], "verified")
    gate(w, exit=0, red_with=["feature.txt"])
    early(w, "S1", "S2")
    assert stacks_asked(w) == [["S1", "S2"], ["run"]]
    text = (w["repo"] / NOTES / f"S2-{tips['S2'][:8]}-without-S1.md").read_text()
    assert ": GREEN" in text.splitlines()[0] and "**Tested again without S1**" in text


def test_a_red_in_the_retest_is_tested_again_without_it_too(world):
    w = world
    tips = three(w, "feature.txt", "S2.txt")
    early(w, "S1", "S2", "S3")
    assert stacks_asked(w) == [["S1", "S2", "S3"], ["S2", "S3"], ["run"]]
    text = (w["repo"] / NOTES / f"S3-{tips['S3'][:8]}-without-S1-S2.md").read_text()
    assert ": GREEN" in text.splitlines()[0] and "**Tested again without S1-S2**" in text


def test_a_stack_may_hold_a_slice_not_yet_verified_and_says_so_for_it(world):
    w = world
    tips = {"S1": w["tip"], **slices(w, "S2")}
    records(w, "S2", tips["S2"], "verifying")
    green_tests(w, "S2", tips["S2"])
    gate(w, exit=0)
    assert early(w, "S1", "S2").returncode == 0
    second = (w["repo"] / NOTES / f"S2-{tips['S2'][:8]}-after-S1.md").read_text()
    assert "(tested, not yet verified)" in second.splitlines()[0]
    assert "not yet verified" not in note(w).read_text().splitlines()[0]


# ------------------------------------------------------------------ 4. broken by what merged ahead, at the top

def moved_path_world(w):
    """main holds an old path; S5 is built on it and names it; then main moves it, as SE6b met this morning."""
    old = w["repo"] / "OspreyFlow_Core/apps/workspace/src/admin/api.ts"
    old.parent.mkdir(parents=True)
    old.write_text("export const api = 1;\n")
    sh("git add -A && git commit -qm 'feat: the admin api'", w["repo"], w["env"])
    sh(["git", "switch", "-q", "-c", "lane/slice-S5"], w["repo"], w["env"])
    t = w["repo"] / "OspreyFlow_Build/tests/test_admin.py"
    t.parent.mkdir(parents=True)
    t.write_text('ADMIN_API = ROOT / "OspreyFlow_Core/apps/workspace/src/admin/api.ts"\n')
    sh("git add -A && git commit -qm 'test: S5 reads the admin api'", w["repo"], w["env"])
    tip = out(["git", "rev-parse", "HEAD"], w["repo"])
    sh(["git", "switch", "-q", "main"], w["repo"], w["env"])
    new = w["repo"] / "OspreyFlow_Core/packages/glass-shared/src/admin/api.ts"
    new.parent.mkdir(parents=True)
    sh(["git", "mv", str(old), str(new)], w["repo"], w["env"])
    sh("git commit -qm 'refactor: the admin api moves to glass-shared'", w["repo"], w["env"])
    records(w, "S5", tip, "verified")
    return tip


def test_a_red_where_main_moved_a_path_the_slice_names_says_so_at_the_top(world):
    w = world
    tip = moved_path_world(w)
    gate(w, exit=1, targets=["test"])
    assert early(w, "S5").returncode == 1
    lines = (w["repo"] / NOTES / f"S5-{tip[:8]}.md").read_text().splitlines()
    assert lines[2].startswith("**Broken by what merged ahead, not by the server.**")
    assert "moved `OspreyFlow_Core/apps/workspace/src/admin/api.ts` to " \
           "`OspreyFlow_Core/packages/glass-shared/src/admin/api.ts`" in lines[2]
    assert "`OspreyFlow_Build/tests/test_admin.py` still names the old path" in lines[2]


def test_a_red_that_names_no_moved_path_says_nothing_of_the_kind(world):
    w = world
    gate(w, exit=1, targets=["test"])
    assert early(w, "S1").returncode == 1
    assert "Broken by what merged ahead" not in note(w).read_text()


def test_a_green_says_nothing_of_the_kind_even_where_a_path_moved(world):
    w = world
    tip = moved_path_world(w)
    gate(w, exit=0)
    assert early(w, "S5").returncode == 0
    assert "Broken by what merged ahead" not in (w["repo"] / NOTES / f"S5-{tip[:8]}.md").read_text()


def test_a_conflict_with_main_says_so_at_the_top(world):
    w = world
    sh(["git", "switch", "-q", "lane/slice-S1"], w["repo"], w["env"])
    (w["repo"] / "shared.txt").write_text("the slice's line\n")
    sh("git add -A && git commit -qm 'feat: S1 changes the shared line'", w["repo"], w["env"])
    tip = out(["git", "rev-parse", "HEAD"], w["repo"])
    sh(["git", "switch", "-q", "main"], w["repo"], w["env"])
    (w["repo"] / "shared.txt").write_text("main's other line\n")
    sh("git add -A && git commit -qm 'docs: main changes the shared line'", w["repo"], w["env"])
    records(w, "S1", tip, "verified")
    assert early(w, "S1").returncode == 1
    lines = note(w, tip).read_text().splitlines()
    assert lines[2].startswith("**Broken by what merged ahead, not by the server.**")
    assert "it does not merge onto main: a conflict in `shared.txt`" in lines[2]


def test_a_stack_red_carried_up_from_a_slice_below_says_whose_it_is(world):
    w = world
    tips = {"S1": w["tip"], **slices(w, "S2")}
    records(w, "S2", tips["S2"], "verified")
    gate(w, exit=0, red_with=["feature.txt"], tests=["t.py::test_it"])
    gate_spec = json.loads(w["gate"].read_text())
    assert gate_spec["tests"] == ["t.py::test_it"]
    early(w, "S1", "S2")
    text = (w["repo"] / NOTES / f"S2-{tips['S2'][:8]}-after-S1.md").read_text().splitlines()
    assert text[2].startswith("**Broken by what merged ahead, not by the server.**")
    assert "also fails for S1, merged before it in this stack, so it is S1's red carried up" in text[2]
    assert "Broken by what merged ahead" not in note(w).read_text()  # S1's own red is its own
