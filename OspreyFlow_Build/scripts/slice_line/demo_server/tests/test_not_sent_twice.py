"""The line-fix session's request of 23 November 2026. On 23 November between 07:13:34 and 07:13:56 SE6c was sent to the
server twice more after its stack's run edfcda0e99098325 had ended with a verdict for that tip on that main; both
ended at once in error, and the merge read the newest. So: a candidate (main, the members below it, the slice, each at
its tip) is not sent again while a run of it has a verdict on the current main, unless --again; and the result's
shape, a stacked member's `stack` above all, is written into early_warning.py's docstring and held to the runner's.
Against the local fake server, with the stand-in gate."""
from __future__ import annotations

import ast
import json
import re
import socket

from conftest import LINE, PROC_HEADER, early, gate, note, out, runner, sh, ssh_calls
from test_013 import NOTES, move_tip, records, run_id
from test_runner import answer
from test_shield import ME, row
from test_stack import slices


def sends(w):
    """The commands that sent work: `run`, or `stack` and its slices."""
    return [c[c.index("stack"):] if "stack" in c else ["run"] for c in ssh_calls(w) if "stack" in c or "run" in c]


def red_for(w, *files):
    gate(w, exit=0, red_with=list(files))


# ------------------------------------------------------------------------------------------------ one slice

def test_a_slice_with_a_verdict_on_this_main_is_not_sent_again_and_its_note_stands(world):
    w = world
    assert early(w, "S1").returncode == 0
    before = note(w).read_text()
    p = early(w, "S1")
    said = p.stdout.decode()
    assert p.returncode == 0 and sends(w) == [["run"]], said
    assert f"S1: not sent again: run {run_id(before)} already gave a verdict for tip {w['tip'][:10]} on this main" \
        in said and "--again sends it anyway" in said
    assert note(w).read_text() == before  # the earlier run's note stands


def test_its_exit_code_is_the_earlier_runs_and_a_red_stays_red(world):
    w = world
    red_for(w, "feature.txt")
    assert early(w, "S1").returncode == 1
    p = early(w, "S1")
    assert p.returncode == 1 and sends(w) == [["run"]] and "(RED:" in p.stdout.decode()


def test_again_sends_it_anyway(world):
    w = world
    early(w, "S1")
    assert early(w, "S1", "--again").returncode == 0 and sends(w) == [["run"], ["run"]]


def test_a_run_that_ended_in_error_is_no_verdict_and_one_behind_it_still_counts(world):
    """This morning's shape: a run with a verdict, then a resend that ended in error at once (the shield refused it).
    The error never stops a send; the verdict behind it does."""
    w = world
    proc = w["tmp"] / "proc-net"
    with socket.socket() as srv:  # a model's helper of another account, reachable: the shield refuses the run
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        (proc / "tcp").write_text(PROC_HEADER + row("0100007F", srv.getsockname()[1], "0A", ME + 1))
        first = early(w, "S1")
        assert first.returncode == 4 and "the shield does not hold" in first.stdout.decode()
        assert early(w, "S1").returncode == 4 and sends(w) == [["run"], ["run"]]  # an error is no verdict
    (proc / "tcp").write_text(PROC_HEADER)
    assert early(w, "S1").returncode == 0 and len(sends(w)) == 3
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        (proc / "tcp").write_text(PROC_HEADER + row("0100007F", srv.getsockname()[1], "0A", ME + 1))
        assert early(w, "S1", "--again").returncode == 4 and len(sends(w)) == 4  # asked: sent, and in error
    (proc / "tcp").write_text(PROC_HEADER)
    p = early(w, "S1")
    assert p.returncode == 0 and len(sends(w)) == 4 and "not sent again" in p.stdout.decode()


def test_once_main_moves_or_the_tip_moves_it_is_sent_again(world):
    w = world
    early(w, "S1")
    (w["repo"] / "main-again.txt").write_text("main moves again\n")
    sh("git add main-again.txt && git commit -qm 'docs: main moves again'", w["repo"], w["env"])
    assert early(w, "S1").returncode == 0 and len(sends(w)) == 2
    tip = move_tip(w)
    records(w, "S1", tip, "verified")
    assert early(w, "S1").returncode == 0 and len(sends(w)) == 3


def test_only_the_servers_own_answer_counts_never_the_record(world):
    """A run the server no longer holds (or never did) is no verdict: the slice is sent."""
    w = world
    early(w, "S1")
    runs = w["data"] / "early-warning" / "runs.jsonl"
    r = json.loads(runs.read_text().splitlines()[-1])
    runs.write_text(json.dumps({**r, "id": "0" * 16}) + "\n")
    assert early(w, "S1").returncode == 0 and len(sends(w)) == 2


def test_the_record_says_which_main_each_run_was_on(world):
    w = world
    early(w, "S1")
    r = json.loads((w["data"] / "early-warning" / "runs.jsonl").read_text().splitlines()[-1])
    assert r["main"] == out(["git", "rev-parse", "main"], w["repo"]) and r["stack"] == ["S1"]


def test_an_old_record_without_its_main_is_decided_by_the_servers_answer(world):
    """Records written before this change have no `main`: the server's result says which main the run was on."""
    w = world
    early(w, "S1")
    runs = w["data"] / "early-warning" / "runs.jsonl"
    r = json.loads(runs.read_text().splitlines()[-1])
    runs.write_text(json.dumps({k: v for k, v in r.items() if k != "main"}) + "\n")
    assert "not sent again" in early(w, "S1").stdout.decode() and len(sends(w)) == 1
    (w["repo"] / "main-again.txt").write_text("main moves again\n")
    sh("git add main-again.txt && git commit -qm 'docs: main moves again'", w["repo"], w["env"])
    assert early(w, "S1").returncode == 0 and len(sends(w)) == 2


# ------------------------------------------------------------------------------------------------ a stack

def two(w):
    tips = {"S1": w["tip"], **slices(w, "S2")}
    records(w, "S2", tips["S2"], "verified")
    return tips


def test_a_stacks_member_already_red_on_this_main_is_left_out_and_the_one_above_is_tested_without_it(world):
    """07:13:34's shape: SE6c red in its own run, then a stack SE6c, DC1b, PL12b sent with it at the bottom again."""
    w = world
    tips = two(w)
    red_for(w, "feature.txt")
    assert early(w, "S1").returncode == 1
    earlier = run_id(note(w).read_text())
    p = early(w, "S1", "S2")
    assert sends(w) == [["run"], ["run"]], p.stdout + p.stderr  # S2 alone: S1 was not sent again
    assert p.returncode == 1  # S1 stays red
    text = (w["repo"] / NOTES / f"S2-{tips['S2'][:8]}-without-S1.md").read_text()
    assert ": GREEN" in text.splitlines()[0]
    assert f"**Tested without S1**, which already had a verdict of red on this main in run `{earlier}`" in text


def test_a_stacks_member_already_green_that_others_stand_on_stops_the_stack_unless_asked(world):
    w = world
    two(w)
    early(w, "S1")
    p = early(w, "S1", "S2")
    assert p.returncode == 2 and sends(w) == [["run"]]
    assert "S1 is green on this main in run" in p.stderr.decode() and "Send it with --again" in p.stderr.decode()
    assert early(w, "S1", "S2", "--again").returncode == 0 and sends(w) == [["run"], ["stack", "S1", "S2"]]


def test_a_stack_whose_every_member_has_a_verdict_is_not_sent_again(world):
    w = world
    two(w)
    assert early(w, "S1", "S2").returncode == 0
    p = early(w, "S1", "S2")
    said = p.stdout.decode()
    assert p.returncode == 0 and sends(w) == [["stack", "S1", "S2"]], said
    assert said.count("not sent again") == 2


def test_a_member_below_whose_tip_moved_makes_a_new_candidate_of_the_one_above(world):
    """The record holds the members' names only; the server's answer holds their tips, and decides."""
    w = world
    two(w)
    assert early(w, "S1", "S2").returncode == 0
    tip = move_tip(w, "S1")
    records(w, "S1", tip, "verified")
    assert early(w, "S1", "S2").returncode == 0
    assert sends(w) == [["stack", "S1", "S2"], ["stack", "S1", "S2"]]


def test_a_stacks_retest_is_its_own_request_and_runs_the_green_ones_below_again(world):
    """013, 3, the owner's ruling: the ones below a red are run again as the base of the ones above. That is the
    request's own retest, not a slice sent again."""
    w = world
    tips = {"S1": w["tip"], **slices(w, "S2", "S3")}
    for n in ("S2", "S3"):
        records(w, n, tips[n], "verified")
    red_for(w, "S2.txt")
    early(w, "S1", "S2", "S3")
    assert sends(w) == [["stack", "S1", "S2", "S3"], ["stack", "S1", "S3"]]


# ------------------------------------------------------------------------------------------------ 2. the result's shape

def test_a_stacked_members_stack_lists_the_members_up_to_and_including_itself(world):
    w = world
    tips = {"S1": w["tip"], **slices(w, "S2", "S3")}
    for n in ("S2", "S3"):
        records(w, n, tips[n], "verified")
    assert early(w, "S1", "S2", "S3").returncode == 0
    lines = [json.loads(x) for x in (w["data"] / "early-warning" / "runs.jsonl").read_text().splitlines()]
    ids = [r["id"] for r in lines]
    stack_id = re.search(r"The stack's run id: `([0-9a-f]{16})`", note(w).read_text()).group(1)
    order = ["S1", "S2", "S3"]
    for k, jid in enumerate(ids):
        d = answer(runner(w, "result " + jid))
        assert d["stack"] == [{"slice": x, "tip": tips[x]} for x in order[:k + 1]]
        assert (d["slice"], d["tip"]) == (order[k], tips[order[k]])
        assert (d["position"], d["of"], d["group"], d["stack_id"]) == (k + 1, 3, ids, stack_id)
        assert d["group"][d["position"] - 1] == jid
    whole = answer(runner(w, "result " + stack_id))
    assert [m["id"] for m in whole["stack"]] == ids and whole["state"] == "done"


def test_a_slice_run_alone_is_a_stack_of_itself_with_no_stack_id(world):
    w = world
    early(w, "S1")
    d = answer(runner(w, "result " + run_id(note(w).read_text())))
    assert d["stack"] == [{"slice": "S1", "tip": w["tip"]}] and (d["position"], d["of"]) == (1, 1)
    assert d["group"] == [d["id"]] and "stack_id" not in d


def test_the_docstring_names_every_field_of_the_runners_result():
    """Every top-level field of a real result (run 97dc976c7be6d175, kept on main by the line-fix session) and of the
    runner's own job result is named in early_warning.py's docstring."""
    doc = ast.get_docstring(ast.parse((LINE / "early_warning.py").read_text()))
    shape = doc[doc.index("The runner's result for one job"):doc.index("Nothing of the setting")]
    real = LINE / "tests" / "fixtures" / "server_result_97dc976c7be6d175.json"
    keys = set(json.loads(real.read_text())) | {"stack_id", "words"}
    missing = sorted(k for k in keys if not re.search(r"\b%s\b" % re.escape(k), shape))
    assert missing == [], missing
    assert "the members up to and including this one, in merge order" in shape
