"""A server stack named on "main plus the train in flight" (the conductor's word of 27 November 2026, on the owner's
freeze: it is what makes the server's second stack usable).

While a train's full gate runs (about an hour), the server's first stack is the train's own and a second stack would
be tested on main without the train: once the train landed, main had moved by the train, and the second stack's green
no longer counted. Now:
- while its gate runs, the train records its tested merge result (trains/inflight.json: the train, its parts, the
  main it started on and the commit gated);
- `early_warning.py <slices> --on-train` sends that commit as the stack's main (the bundle's refs/heads/main), so the
  server tests the second stack on main plus the train;
- at a part's merge, a server result on a train's gated commit counts once that train has landed, provided main has
  moved since only by that train and records commits (the train's own records commits under its gate included); the
  trees are checked as for records commits (item 4): the Mac's candidate differs from the server's in exactly the
  records commits' files. Main moved otherwise (another part, a plain commit, a train that did not land): not counted.

The world is the train's (test_merge_train: S1, T2 and T3 verified, the switch on), with the server's results stood in
as in test_server_stack.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from test_gates import built, sh, verified, world  # noqa: F401  (world is a fixture)
from test_merge_train import ROWS, V062, main_sha, part, records_during, set_state, train, trains
from test_server_counts import makefiles
from test_server_slot import FAKE_EW, RID, switch
from test_server_stack import PASSED, merge_of


@pytest.fixture
def tw(world):
    """S1, T2 and T3 verified, the train switch on, the server's counting on and its results stood in."""
    w = world
    makefiles(w)
    (w["lines"] / "early_warning.py").write_text(FAKE_EW)
    with (w["repo"] / V062 / "slices.tsv").open("a") as fh:
        fh.write(ROWS)
    sh("git add -A && git commit -qm 'test: the early warning stood in; two more parts' && git push -q origin main",
       w["repo"], w["env"])
    w["env"]["TEST_EW_RESULTS"] = str(w["tmp"] / "ew")
    (w["tmp"] / "ew").mkdir(exist_ok=True)
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, "S1", phase="verified", tip=tip)
    w["tips"] = {"S1": tip, "T2": part(w, "T2"), "T3": part(w, "T3")}
    (w["data"] / "merge_train").write_text("on\n")
    switch(w)
    return w


def server_pass_on(w, sid, base):
    """The server's pass for `sid` alone, tested on `base` (the train's gated commit), with its note."""
    tip = w["tips"][sid]
    tree = sh(["git", "merge-tree", "--write-tree", base, tip], w["repo"]).stdout.split()[0]
    r = {"state": "done", "id": RID, "slice": sid, "main": base, "tip": tip, "tree": tree, "verdict": "pass",
         "failing": {"tests": [], "targets": []}, "passed_targets": PASSED, "not_run": {}}
    (w["tmp"] / "ew" / f"{RID}.json").write_text(json.dumps(r))
    d = w["repo"] / V062 / "early_warning"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}-{tip[:8]}.md").write_text(f"# Early warning: {sid} at {tip[:8]}: GREEN\n\n- Run id: `{RID}`\n")
    return r


def train_with_records_under_its_gate(w):
    seen = w["tmp"] / "inflight.json"
    during = records_during(w, f"{V062}/records-note.md") + f"; if [ -s {w['data']}/trains/inflight.json ]; then cp {w['data']}/trains/inflight.json {seen}; fi"
    p, runs = train(w, "S1", "T2", during=during)
    t = trains(w)[-1]
    assert p.returncode == 0 and t["result"] == "merged" and t.get("records_under_gate"), (t, p.stdout + p.stderr)
    return t, json.loads(seen.read_text()) if seen.exists() and seen.read_text().strip() else {}


def test_while_a_trains_gate_runs_it_records_the_commit_it_gates(tw):
    w = tw
    base = main_sha(w)
    t, inflight = train_with_records_under_its_gate(w)
    assert inflight.get("gated") == t["gated"] and inflight.get("parts") == ["S1", "T2"], inflight
    assert inflight.get("base") == base and inflight.get("train") == t["train"], inflight
    assert not (w["data"] / "trains/inflight.json").exists(), "the in-flight record outlived its train"


def test_a_second_stacks_green_on_the_train_counts_once_the_train_has_landed(tw):
    """Main moved since the server's run only by the train (its parts made again over a records commit under its gate)
    and a records commit after it: the server's green on the train's gated commit stands for T3's merge."""
    w = tw
    t, _ = train_with_records_under_its_gate(w)
    server_pass_on(w, "T3", t["gated"])
    sh(f"mkdir -p {V062} && echo m > {V062}/after.md && git add {V062}/after.md && "
       "git commit -qm 'docs: after the train' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    p, plan, server = merge_of(w, "T3")
    assert p.returncode == 0, p.stdout + p.stderr
    assert server and server["counted"] is True and server["run_id"] == RID, server
    # the records commits (the train's own under its gate, and the one after it) are all main moved by besides the train
    assert server["records_moved"] == sorted([f"{V062}/records-note.md", f"{V062}/after.md"]), server
    # so the Mac runs only what reads the records folder (item 5), never the gate's own test target
    assert isinstance(plan, list) and ["make", "-k", "client-name-check"] in plan, plan
    assert not any("test" in x[2:] for x in plan if x[:2] == ["make", "-k"]), plan


def test_a_second_stacks_green_on_the_train_is_not_counted_when_main_moved_otherwise(tw):
    w = tw
    t, _ = train_with_records_under_its_gate(w)
    server_pass_on(w, "T3", t["gated"])
    sh("echo other > other.txt && git add other.txt && git commit -qm 'feat: something else on main'", w["repo"], w["env"])
    p, plan, server = merge_of(w, "T3")
    assert p.returncode == 0, p.stdout + p.stderr
    assert server and server["counted"] is False and server.get("why"), server
    assert plan is None, plan                                  # the Mac runs its whole gate itself (no remainder)


def test_a_green_on_a_train_that_did_not_land_is_not_counted(tw):
    """The train's gate red: its parts merged alone, and the commit it gated (the second stack's base) never landed."""
    w = tw
    seen = w["tmp"] / "inflight.json"
    p, runs = train(w, "S1", "T2", gate_run='case "$PWD" in *slice-train-*) exit 1;; esac; exit 0',
                    during=f"if [ -s {w['data']}/trains/inflight.json ]; then cp {w['data']}/trains/inflight.json {seen}; fi")
    t = trains(w)[-1]
    gated = json.loads(seen.read_text())["gated"]
    assert t["result"] == "each alone" and gated, t
    server_pass_on(w, "T3", gated)
    p, plan, server = merge_of(w, "T3")
    assert server and server["counted"] is False, server


def test_on_train_sends_the_trains_gated_commit_as_the_stacks_main(world):
    w = world
    gated = sh("git commit-tree HEAD^{tree} -p HEAD -m 'a train candidate'", w["repo"], w["env"]).stdout.strip()
    (w["data"] / "trains").mkdir(parents=True, exist_ok=True)
    (w["data"] / "trains/inflight.json").write_text(json.dumps(
        {"train": "train-0000aaaa", "parts": ["S2"], "base": main_sha(w), "gated": gated}))
    bundle = w["tmp"] / "b.bundle"
    sh("git branch lane/slice-S1 HEAD", w["repo"], w["env"])
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); from pathlib import Path; import early_warning as ew; "
            f"ew.make_bundle(['lane/slice-S1'], Path({str(bundle)!r}), True, base=ew.train_base(['S1'])['gated'])")
    p = sh([w["py"], "-c", code], w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    heads = dict(reversed(x.split()) for x in sh(["git", "bundle", "list-heads", str(bundle)], w["repo"]).stdout.splitlines())
    assert heads.get("refs/heads/main") == gated and "refs/heads/lane/slice-S1" in heads, heads
    assert sh("git rev-parse main", w["repo"]).stdout.strip() != gated      # the Mac's own main untouched


@pytest.mark.parametrize("inflight, words", [
    (None, "no train is in flight"),
    ({"train": "train-0000aaaa", "parts": ["S1"], "base": "", "gated": ""}, "S1 is in the train"),
], ids=["no-train", "a-part-of-the-train"])
def test_on_train_is_refused_with_no_train_in_flight_or_for_a_part_of_it(world, inflight, words):
    w = world
    if inflight:
        inflight = {**inflight, "base": main_sha(w), "gated": main_sha(w)}
        (w["data"] / "trains").mkdir(parents=True, exist_ok=True)
        (w["data"] / "trains/inflight.json").write_text(json.dumps(inflight))
    p = subprocess.run([w["py"], str(w["lines"] / "early_warning.py"), "S1", "S2", "--on-train"], cwd=w["repo"],
                       env=w["env"], capture_output=True, text=True)
    assert p.returncode != 0 and words in p.stderr, p.stdout + p.stderr
