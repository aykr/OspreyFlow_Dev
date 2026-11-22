"""009, item 1: a stack run. Given slices in merge order (A, B, C), the runner tests main+A, main+A+B and main+A+B+C
at the same time, one job each, each candidate merged in that order as the Mac's merge would make it, each in its own
port slot; and refuses what is not exactly that. Against the local fake server, with the stand-in gate."""
from __future__ import annotations

import json
import time

from conftest import out, runner, sh
from test_runner import answer, bundle_of, wait

import protocol


def slices(w, *names, shared=None):
    """Branches lane/slice-<name> from main, each adding its own file (or, with `shared`, changing one shared file)."""
    tips = {}
    for n in names:
        sh(["git", "switch", "-q", "-c", f"lane/slice-{n}", "main"], w["repo"], w["env"])
        f = w["repo"] / (shared or f"{n}.txt")
        f.write_text(f"{n}'s work\n")
        sh(f"git add -A && git commit -qm 'feat: {n}'", w["repo"], w["env"])
        tips[n] = out(["git", "rev-parse", "HEAD"], w["repo"])
    sh(["git", "switch", "-q", "main"], w["repo"], w["env"])
    return tips


def stack_bundle(w, *names):
    return bundle_of(w, "refs/heads/main", *[f"refs/heads/lane/slice-{n}" for n in names])


def expected_tree(w, *names):
    """The candidate as the Mac's merge makes it: main, then each slice merged --no-ff in that order."""
    clone = w["tmp"] / ("expect-" + "-".join(names))
    sh(["git", "clone", "-q", str(w["repo"]), str(clone)], w["tmp"], w["env"])
    sh(["git", "switch", "-q", "main"], clone, w["env"])
    for n in names:
        sh(["git", "merge", "--no-ff", "-q", "-m", f"merge {n}", f"origin/lane/slice-{n}"], clone, w["env"])
    return out(["git", "rev-parse", "HEAD^{tree}"], clone)


def stack_started(w, *names, **gate):
    w["gate"].write_text(json.dumps(gate or {"exit": 0}))
    p = runner(w, "stack " + " ".join(names), stack_bundle(w, *names))
    a = answer(p)
    assert p.returncode == 0 and a["state"] == "started", a
    return a


def test_a_stack_tests_each_candidate_at_once_one_job_each_in_merge_order(world):
    w = world
    tips = {"S1": w["tip"], **slices(w, "S2", "S3")}
    a = stack_started(w, "S1", "S2", "S3", exit=0, sleep=3)
    ids, stack_id = a["ids"], a["id"]
    assert len(ids) == 3 == len(set(ids)) and a["stack"] == ["S1", "S2", "S3"] and stack_id not in ids
    time.sleep(1)
    assert [answer(runner(w, "result " + j))["state"] for j in ids] == ["running"] * 3  # at the same time
    assert answer(runner(w, "result " + stack_id))["state"] == "running"  # the stack's one result (012 c)
    done = [wait(w, j) for j in ids]
    whole = wait(w, stack_id)
    assert whole["state"] == "done" and whole["id"] == stack_id and whole["main"] == done[0]["main"]
    assert [m["slice"] for m in whole["stack"]] == ["S1", "S2", "S3"]  # in the order run
    for m, r in zip(whole["stack"], done):
        assert m == {"id": r["id"], "state": "done", **{k: r.get(k) for k in
                     ("slice", "tip", "tree", "verdict", "failing", "passed_targets", "not_run")}}
        assert r["stack_id"] == stack_id
    for k, r in enumerate(done):
        names = ["S1", "S2", "S3"][:k + 1]
        assert r["state"] == "done" and r["verdict"] == "pass", r
        assert r["stack"] == [{"slice": n, "tip": tips[n]} for n in names]
        assert (r["position"], r["of"], r["group"]) == (k + 1, 3, ids)
        assert r["slice"] == names[-1] and r["tip"] == tips[names[-1]]
        assert r["tree"] == expected_tree(w, *names), names  # exactly the tree the Mac's merges in that order give
        assert len(r["merges"]) == k + 1
    assert len({r["lane"] for r in done}) == 3  # three port slots, never shared
    assert len({r["tree"] for r in done}) == 3


def test_a_stack_bundle_carries_exactly_the_slices_named(world):
    w = world
    slices(w, "S2", "S3")
    p = runner(w, "stack S1 S2", stack_bundle(w, "S1", "S2", "S3"))  # one more than named
    assert p.returncode == 3 and answer(p)["reason"] == "bundle-heads"
    p = runner(w, "stack S1 S2 S3", stack_bundle(w, "S1", "S2"))  # one fewer
    assert p.returncode == 3 and answer(p)["reason"] == "bundle-heads"
    assert list((w["remote"] / "data/jobs").iterdir()) == []
    assert out(["git", "for-each-ref", "refs/early/"], w["remote"] / "data/source.git") == ""  # nothing left held


def test_a_stack_waits_for_enough_free_slots(world):
    w = world
    slices(w, "S2", "S3")
    w["gate"].write_text(json.dumps({"exit": 0, "sleep": 3}))
    one = answer(runner(w, "run", bundle_of(w, "refs/heads/main", "refs/heads/lane/slice-S1")))
    p = runner(w, "stack S1 S2 S3", stack_bundle(w, "S1", "S2", "S3"))
    assert p.returncode == 3 and answer(p) == {"state": "refused", "reason": "busy", "running": [one["id"]],
                                                "free": protocol.MAX_JOBS - 1}
    wait(w, one["id"])


def test_a_stack_whose_later_slice_conflicts_names_it_and_the_ones_before(world):
    w = world
    slices(w, "S2", "S3", shared="shared.txt")  # S2 and S3 both change shared.txt
    a = stack_started(w, "S1", "S2", "S3")
    r1, r2, r3 = (wait(w, j) for j in a["ids"])
    assert r1["verdict"] == "pass" and r2["verdict"] == "pass"
    assert r3["verdict"] == "conflict" and r3["conflict_slice"] == "S3" and r3["conflicts"] == ["shared.txt"]
    assert "S3 does not merge cleanly onto main with S1, S2 merged first" == r3["words"]


def test_the_forced_command_takes_two_or_three_different_slices_and_nothing_else():
    assert protocol.parse_command("stack PL4d3e IS5a0 DC1c") == ("stack", "PL4d3e IS5a0 DC1c")
    assert protocol.parse_command("stack A B") == ("stack", "A B")
    for bad in ("stack A", "stack A B C D", "stack A A", "stack A  B", "stack A B;ls", "stack A-1 B", "stack A B ",
                "stack ../x B", "stack " + "A" * 17 + " B"):
        assert protocol.parse_command(bad) == (None, "shape"), bad
