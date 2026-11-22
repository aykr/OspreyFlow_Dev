"""009, item 3: a result the merge can rely on without a person. `early_warning.py <slice> --trust <id> --tree <hash>`
asks the server itself for the run by its id, over the forced command, and never reads a note; it trusts the run only
for the exact candidate tree, for that slice at that tip, with every target the tree's own Makefiles name accounted
for and none failed. The note carries the same lists for a reader, and proves nothing. Against the local fake server."""
from __future__ import annotations

import json
import re

import pytest

from conftest import early, gate, note, out, sh, ssh_calls
from test_stack import slices

PASSED = [{"name": "a-check", "kind": "ci", "status": "passed"}, {"name": "lint", "kind": "core", "status": "passed"},
          {"name": "client-name-check", "kind": "ci", "status": "not run", "why": "client-names"},
          {"name": "test", "kind": "test", "status": "passed"}]


def makefiles(w):
    """main gains the two Makefiles the candidate's checks are read from."""
    for rel, text in {"OspreyFlow_Build/Makefile": "ci: core-check a-check client-name-check\n",
                      "OspreyFlow_Core/Makefile": "check: lint\n"}.items():
        (w["repo"] / rel).parent.mkdir(parents=True, exist_ok=True)
        (w["repo"] / rel).write_text(text)
    sh("git add -A && git commit -qm 'chore: the Makefiles'", w["repo"], w["env"])


def green_run(w, checks=PASSED, **spec):
    makefiles(w)
    gate(w, exit=0, checks=checks, **spec)
    p = early(w, "S1")
    text = note(w).read_text()
    jid = re.search(r"Run id: `([0-9a-f]{16})`", text).group(1)
    tree = re.search(r"Candidate tree hash: `([0-9a-f]{40})`", text).group(1)
    # the merge's own candidate, built on this machine first, as merge_slice.py builds it before it asks
    assert out(["git", "merge-tree", "--write-tree", "main", w["tip"]], w["repo"]).splitlines()[0] == tree
    return p, jid, tree


def trust(w, jid, tree, env=None):
    p = early(w, "S1", "--trust", jid, "--tree", tree, env=env)
    return p.returncode, json.loads(p.stdout.decode())


def test_a_green_run_of_this_exact_tree_is_trusted_and_says_what_the_mac_must_still_run(world):
    w = world
    p, jid, tree = green_run(w)
    assert p.returncode == 0
    code, said = trust(w, jid, tree)
    assert code == 0 and said["trusted"] is True, said
    assert said["passed"] == ["a-check", "lint", "test"] and said["tree"] == tree and said["tip"] == w["tip"]
    assert said["mac_must_run"]["targets"] == ["client-name-check"] and said["mac_must_run"]["live_step"] is True
    assert ssh_calls(w)[-1][-2:] == ["result", jid]  # asked of the server, by its id


def test_the_note_carries_the_lists_for_scripts_and_says_it_proves_nothing(world):
    w = world
    _, jid, tree = green_run(w)
    text = note(w).read_text()
    block = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])
    assert block["run_id"] == jid and block["tree"] == tree and block["verdict"] == "pass"
    assert (block["passed"], block["failed"], block["not_run"]) == (["a-check", "lint", "test"], [],
                                                                    ["client-name-check"])
    assert "a note written by hand proves nothing" in text


def test_a_note_written_by_hand_never_counts(world):
    w = world
    makefiles(w)
    tree = out(["git", "merge-tree", "--write-tree", "main", w["tip"]], w["repo"]).splitlines()[0]
    fake = "feedfacefeedface"
    block = {"run_id": fake, "slice": "S1", "tip": w["tip"], "tree": tree, "verdict": "pass",
             "runner_version": "ew-2", "passed": ["a-check", "lint", "test"], "failed": [], "not_run": []}
    note(w).parent.mkdir(parents=True, exist_ok=True)
    note(w).write_text(f"# Early warning: S1 at {w['tip'][:8]}: GREEN\n\n- Run id: `{fake}`\n\n```json\n"
                       f"{json.dumps(block)}\n```\n")
    code, said = trust(w, fake, tree)
    assert code == 1 and said["trusted"] is False and "holds no finished run" in said["why"]


def test_a_red_run_is_not_trusted_even_where_its_note_was_edited_to_green(world):
    w = world
    makefiles(w)
    gate(w, exit=1, targets=["a-check"], checks=[{**PASSED[0], "status": "failed"}, *PASSED[1:]])
    assert early(w, "S1").returncode == 1
    text = note(w).read_text()
    jid = re.search(r"Run id: `([0-9a-f]{16})`", text).group(1)
    tree = re.search(r"Candidate tree hash: `([0-9a-f]{40})`", text).group(1)
    out(["git", "merge-tree", "--write-tree", "main", w["tip"]], w["repo"])
    note(w).write_text(text.replace("RED", "GREEN").replace('"verdict": "fail"', '"verdict": "pass"'))
    code, said = trust(w, jid, tree)
    assert code == 1 and said["trusted"] is False and "verdict is fail" in said["why"]


def test_a_run_of_another_tree_is_not_trusted(world):
    w = world
    _, jid, tree = green_run(w)
    other = out(["git", "rev-parse", "main^{tree}"], w["repo"])
    code, said = trust(w, jid, other)
    assert code == 1 and "not this candidate's" in said["why"]


@pytest.mark.parametrize("left_out", ["a-check", "lint", "test"])
def test_a_target_the_result_does_not_account_for_is_not_trusted(world, left_out):
    w = world
    _, jid, tree = green_run(w, checks=[x for x in PASSED if x["name"] != left_out])
    code, said = trust(w, jid, tree)
    assert code == 1 and said["why"] == "the result does not say what became of " + left_out


def test_a_run_by_a_runner_with_no_check_per_target_is_not_trusted(world):
    w = world
    _, jid, tree = green_run(w)
    res = w["remote"] / "data/jobs" / jid / "result.json"
    res.write_text(json.dumps({**json.loads(res.read_text()), "runner_version": "ew-1"}))
    code, said = trust(w, jid, tree)
    assert code == 1 and "records no check per target" in said["why"]


def test_a_run_for_another_slice_tip_is_not_trusted(world):
    w = world
    _, jid, tree = green_run(w)
    sh(["git", "switch", "-q", "lane/slice-S1"], w["repo"], w["env"])
    (w["repo"] / "more.txt").write_text("a later commit\n")
    sh("git add -A && git commit -qm 'feat: S1 moves on'", w["repo"], w["env"])
    sh(["git", "switch", "-q", "main"], w["repo"], w["env"])
    code, said = trust(w, jid, tree)
    assert code == 1 and "not S1 at" in said["why"]


def test_an_unreachable_server_is_no_answer_and_never_trusted(world):
    w = world
    _, jid, tree = green_run(w)
    code, said = trust(w, jid, tree, env={"FAKE_SSH": "down"})
    assert code == 4 and said["trusted"] is False


def test_a_stack_writes_one_note_per_candidate_naming_its_stack(world):
    w = world
    tips = slices(w, "S2")
    rec = w["data"] / "records" / "S2"
    rec.mkdir(parents=True)
    (rec / "frozen.json").write_text(json.dumps({"branch": "lane/slice-S2", "acceptance": "true"}))
    (rec / "state.json").write_text(json.dumps({"phase": "verified", "tip": tips["S2"]}))
    p = early(w, "S1", "S2")
    assert p.returncode == 0, p.stdout + p.stderr
    assert ssh_calls(w)[0][-2:] == ["stack", "S1", "S2"] or ssh_calls(w)[0][-3:] == ["stack", "S1", "S2"]
    first = note(w).read_text()
    second = (note(w).parent / f"S2-{tips['S2'][:8]}-after-S1.md").read_text()
    assert "GREEN" in first and "GREEN" in second
    assert f"- Stack: candidate 2 of 2, main + S1 `{w['tip'][:10]}` + S2 `{tips['S2'][:10]}`" in second


def test_auto_asks_the_server_about_the_runs_recorded_here_and_trusts_only_its_answer(world):
    w = world
    _, jid, tree = green_run(w)
    code, said = trust(w, "auto", tree)
    assert code == 0 and said["trusted"] is True and said["run_id"] == jid
    assert ssh_calls(w)[-1][-2:] == ["result", jid]
    res = w["remote"] / "data/jobs" / jid / "result.json"
    res.write_text(json.dumps({**json.loads(res.read_text()), "verdict": "fail"}))  # the server's word changes
    code, said = trust(w, "auto", tree)
    assert code == 1 and said["trusted"] is False and "verdict is fail" in said["why"]


def test_auto_asks_about_the_run_of_this_tree_not_a_newer_run_of_another(world):
    w = world
    _, jid, tree = green_run(w)
    with (w["data"] / "early-warning/runs.jsonl").open("a") as fh:  # a later run of S1 at its tip, in a stack: another tree
        fh.write(json.dumps({"slice": "S1", "tip": w["tip"], "id": "0123456789abcdef", "tree": "1" * 40}) + "\n")
    code, said = trust(w, "auto", tree)
    assert code == 0 and said["run_id"] == jid


def test_auto_with_no_recorded_run_is_not_trusted(world):
    w = world
    makefiles(w)
    tree = out(["git", "merge-tree", "--write-tree", "main", w["tip"]], w["repo"]).splitlines()[0]
    (w["data"] / "early-warning").mkdir(parents=True, exist_ok=True)
    (w["data"] / "early-warning/runs.jsonl").write_text(json.dumps(  # another slice's run is no run of S1's
        {"slice": "S2", "tip": "2" * 40, "id": "0123456789abcdef", "tree": tree}) + "\n")
    code, said = trust(w, "auto", tree)
    assert code == 1 and said["trusted"] is False and said["why"].startswith("no run of S1")
