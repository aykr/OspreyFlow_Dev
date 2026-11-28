"""The owner's ask of 26 November 2026, item 3: a merge train, behind the owner's switch merge_train ("on" only; off
as built). Up to three verified parts merged together and tested as one: each part's own merge steps run as its merge
runs them, each on the candidate before it (main, then main and the parts before it); one full gate on the last
candidate. Green: main is fast-forwarded to it, through each part's own merge commit in order. Red, or any part's own
step not passing on the train's candidate, or main moving meanwhile: nothing is recorded against any part, and each
part is merged alone, in order, by its own merge, which blames only its own red.

The world is the line's own (test_gates), with two more parts in its backlog (T2, T3), each with its own files. The
full gate is stood in: TEST_GATE_RUN runs in the gate's tree (a train's tree is named slice-train-...), and each gate
run is counted.
"""
from __future__ import annotations

import json

import pytest

from test_gates import built, sh, verified, world  # noqa: F401  (world is a fixture)

ROWS = ("T2\tCO1\tThe second part\t-\t1\t-\tnone\taccept_t2.sh\tsh accept_t2.sh\ttrue\n"
        "T3\tCO1\tThe third part\t-\t1\t-\tnone\taccept_t3.sh\tsh accept_t3.sh\ttrue\n")
V062 = "OspreyFlow_Build/process/lanes/v062"
TRAIN_TREE_RED = 'case "$PWD" in *slice-train-*) exit 1;; esac; exit 0'


def set_state(w, sid, **kv):
    f = w["data"] / f"records/{sid}/state.json"
    f.write_text(json.dumps({**json.loads(f.read_text()), **kv}))


def verify(w, sid, tip):
    t = w["tmp"] / f"transcript-{sid}.jsonl"
    t.write_text(json.dumps({"type": "assistant", "text": f"pass {tip}"}) + "\n")
    (w["data"] / f"records/{sid}/verify-{tip}.json").write_text(json.dumps({
        "slice": sid, "commit": tip, "verdict": "pass",
        "passes": [{"pass": "acceptance", "verdict": "pass", "commit": tip, "session": f"v-{sid}", "transcript": str(t)}]}))
    set_state(w, sid, phase="verified", tip=tip)


def part(w, sid, accept=None):
    """A part built and verified: its acceptance red on main, green with its own file."""
    p = sh([w["py"], str(w["lines"] / "slice_start.py"), sid], w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    wt = w["tmp"] / "wt" / f"slice-{sid}"
    n = sid.lower()
    (wt / f"accept_{n}.sh").write_text((accept or f"test -f {n}.txt") + "\n")
    sh(f"git add accept_{n}.sh && git commit -qm 'test: {sid} acceptance, red'", wt, w["env"])
    (wt / f"{n}.txt").write_text("done\n")
    sh(f"git add {n}.txt && git commit -qm 'feat: {sid}'", wt, w["env"])
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    verify(w, sid, tip)
    return tip


@pytest.fixture
def tw(world):
    """S1, T2 and T3 verified; the switch on."""
    w = world
    with (w["repo"] / V062 / "slices.tsv").open("a") as fh:
        fh.write(ROWS)
    sh("git add -A OspreyFlow_Build/process && git commit -qm 'two more parts' && git push -q origin main", w["repo"],
       w["env"])
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, "S1", phase="verified", tip=tip)
    w["tips"] = {"S1": tip, "T2": part(w, "T2"), "T3": part(w, "T3")}
    (w["data"] / "merge_train").write_text("on\n")
    return w


def train(w, *ids, gate_run=None, during=None):
    count = w["tmp"] / "gates.count"
    count.unlink(missing_ok=True)
    env = {**w["env"], "TEST_GATE": "0", "TEST_GATE_DURING": f"echo x >> {count}" + (f"; {during}" if during else ""),
           "TEST_GATE_DURING_CWD": str(w["repo"])}
    if gate_run:
        env["TEST_GATE_RUN"] = gate_run
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "train", *ids], w["repo"], env, check=False)
    runs = len(count.read_text().split()) if count.exists() else 0
    return p, runs


def main_sha(w):
    return sh("git rev-parse main", w["repo"]).stdout.strip()


def first_parents(w, n):
    return sh(f"git log --first-parent --format=%s -{n} main", w["repo"]).stdout.splitlines()


def merged(w, sid):
    f = w["data"] / f"records/{sid}/merged.json"
    return json.loads(f.read_text()) if f.exists() else None


def trains(w):
    f = w["data"] / "trains/trains.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


def refusals(w):
    f = w["data"] / "refusals.tsv"
    return [ln.split("\t")[1] for ln in f.read_text().splitlines()[1:]] if f.exists() else []


def test_a_green_train_lands_all_three_in_order_on_one_gate(tw):
    w = tw
    base = main_sha(w)
    p, runs = train(w, "S1", "T2", "T3")
    assert p.returncode == 0, p.stdout + p.stderr
    assert runs == 1, runs                                                    # one full gate for the three
    assert [s.split()[2] for s in first_parents(w, 3)] == ["T3", "T2", "S1"], first_parents(w, 3)
    t = trains(w)[-1]
    assert t["result"] == "merged" and t["parts"] == ["S1", "T2", "T3"] and t["gated"] == main_sha(w), t
    chain = sh(f"git rev-list --first-parent {base}..main", w["repo"]).stdout.split()[::-1]
    for sid, commit in zip(("S1", "T2", "T3"), chain):
        m = merged(w, sid)
        assert m["merge"] == commit and m["tip"] == w["tips"][sid] and m["train"]["gated"] == main_sha(w), m
        assert json.loads((w["data"] / f"records/{sid}/state.json").read_text())["phase"] == "merged"
    assert sh(f"git merge-base --is-ancestor {base} main", w["repo"]).returncode == 0       # a fast-forward of main


def test_a_train_of_two_lands_both(tw):
    w = tw
    p, runs = train(w, "S1", "T2")
    assert p.returncode == 0 and runs == 1 and merged(w, "S1")["train"]["parts"] == ["S1", "T2"], p.stderr
    assert merged(w, "T2")["train"]["gated"] == main_sha(w) and merged(w, "T3") is None


def test_a_red_train_gate_blames_no_one_and_each_part_merges_alone(tw):
    w = tw
    base = main_sha(w)
    p, runs = train(w, "S1", "T2", "T3", gate_run=TRAIN_TREE_RED)
    assert p.returncode == 0, p.stdout + p.stderr
    assert runs == 4, runs                                                    # the train's gate, then each part's own
    t = trains(w)[-1]
    assert t["result"] == "each alone" and "full gate" in t["why"] and "red" in t["why"], t
    out = json.loads(p.stdout)
    assert [a["result"] for a in out["alone"]] == ["merged", "merged", "merged"], out
    for sid in ("S1", "T2", "T3"):
        assert "train" not in merged(w, sid), merged(w, sid)                   # each landed by its own merge
        assert not (w["data"] / f"records/{sid}/verify-gate-{w['tips'][sid]}.json").exists()
    assert refusals(w) == [], refusals(w)
    assert [s.split()[2] for s in first_parents(w, 3)] == ["T3", "T2", "S1"]
    assert sh(f"git merge-base --is-ancestor {base} main", w["repo"]).returncode == 0


def test_a_part_red_on_the_train_s_candidate_stops_the_train_and_only_its_own_merge_judges_it(world):
    """T2 is red whenever S1's file is in the tree. In the train it is red on main and S1: the train stops, nothing is
    recorded. Merged alone after S1, T2 is red on main as it then is, and its own merge records that."""
    w = world
    with (w["repo"] / V062 / "slices.tsv").open("a") as fh:
        fh.write(ROWS)
    sh("git add -A OspreyFlow_Build/process && git commit -qm 'two more parts' && git push -q origin main", w["repo"],
       w["env"])
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, "S1", phase="verified", tip=tip)
    t2 = part(w, "T2", accept="test -f t2.txt && test ! -f feature.txt")
    t3 = part(w, "T3")
    (w["data"] / "merge_train").write_text("on\n")
    p, runs = train(w, "S1", "T2", "T3")
    t = trains(w)[-1]
    assert t["result"] == "each alone" and t["why"].startswith("T2: "), t
    out = json.loads(p.stdout)
    assert [(a["slice"], a["result"]) for a in out["alone"]] == [("S1", "merged"), ("T2", "refused"), ("T3", "merged")]
    assert runs == 2, runs                                    # no train gate; S1's and T3's own
    assert refusals(w) == ["T2"], refusals(w)                 # one refusal, T2's own merge's, none from the train
    progress = sorted((w["data"] / "records/T2").glob("merge-progress-*.json"))
    results = [json.loads(f.read_text())["result"] for f in progress]
    assert sorted(results) == ["in a train that stopped", "refused"], results


def test_a_part_red_only_beside_another_carries_no_blame_from_the_train(world):
    """T2 is red only with S1's file in the tree. The train stops at T2, on main and S1. Alone, S1 is red on its own
    gate and is refused; T2, alone on main without S1, merges, with no finding or refusal left from the train."""
    w = world
    with (w["repo"] / V062 / "slices.tsv").open("a") as fh:
        fh.write(ROWS)
    sh("git add -A OspreyFlow_Build/process && git commit -qm 'two more parts' && git push -q origin main", w["repo"],
       w["env"])
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, "S1", phase="verified", tip=tip)
    t2 = part(w, "T2", accept="test -f t2.txt && test ! -f feature.txt")
    (w["data"] / "merge_train").write_text("on\n")
    p, runs = train(w, "S1", "T2", gate_run='[ ! -f feature.txt ]')   # a gate red wherever S1's file is
    out = json.loads(p.stdout)
    assert [(a["slice"], a["result"]) for a in out["alone"]] == [("S1", "refused"), ("T2", "merged")], out
    assert not (w["data"] / f"records/T2/verify-gate-{t2}.json").exists()
    assert refusals(w) == ["S1"], refusals(w)
    assert json.loads((w["data"] / "records/T2/state.json").read_text())["phase"] == "merged"


def records_during(w, rel):
    """A records commit (merge_slice.py records) of rel, once, while the train's gate runs."""
    return (f"[ -f {w['tmp']}/once ] || {{ touch {w['tmp']}/once; mkdir -p $(dirname {rel}); echo n > {rel}; "
            f"{w['py']} {w['lines']}/merge_slice.py records -m 'a records commit' {rel} >/dev/null; }}")


def test_a_records_commit_during_the_train_s_gate_lands_beneath_the_train(tw):
    """The conductor's records commits come about one an hour, a train's gate takes about an hour (26 November 2026):
    a records commit lands beneath the train, as beneath a single merge (land()). Each part's merge commit is made
    again on the moved main, in order, its tree the tested one plus the records commit's file, and names the commit
    tested; one gate still."""
    w = tw
    base = main_sha(w)
    rec = f"{V062}/records-note.md"
    p, runs = train(w, "S1", "T2", "T3", during=records_during(w, rec))
    t = trains(w)[-1]
    assert p.returncode == 0 and t["result"] == "merged", (t, p.stdout + p.stderr)
    assert runs == 1, runs
    assert [s.split()[2] for s in first_parents(w, 3)] == ["T3", "T2", "S1"], first_parents(w, 4)
    under = sh(f"git rev-list --first-parent {base}..main", w["repo"]).stdout.split()[::-1]
    records_commit, chain = under[0], under[1:]
    assert "Slice-Records: yes" in sh(f"git log -1 --format=%B {records_commit}", w["repo"]).stdout
    assert t["gated"] != main_sha(w) and t["landed"] == main_sha(w) and t["records_under_gate"] == [records_commit], t
    for sid, commit in zip(("S1", "T2", "T3"), chain):
        m = merged(w, sid)
        assert m["merge"] == commit and m["records_under_gate"] == [records_commit], m
        assert m["train"]["gated"] == t["gated"] and m["tested_merge"] != commit, m
        assert f"Slice-Tested: {m['tested_merge']}" in sh(f"git log -1 --format=%B {commit}", w["repo"]).stdout
        assert sh(f"git rev-parse {commit}^2", w["repo"]).stdout.strip() == w["tips"][sid]
        # each made again differs from its tested merge in the records commit's file alone
        assert sh(f"git diff --name-only {m['tested_merge']} {commit}", w["repo"]).stdout.split() == [rec]
    assert sh(f"git diff --name-only {t['gated']} main", w["repo"]).stdout.split() == [rec]
    assert (w["repo"] / rec).read_text() == "n\n" and refusals(w) == []


@pytest.mark.parametrize("what, words", [
    ("plain", "not a records commit"),
    ("scan_rows", "a path the gate tested"),
])
def test_main_moved_by_anything_but_a_plain_records_commit_lands_nothing_of_the_train(tw, what, words):
    """Anything else moving main under the train's gate (a commit that is not a records commit, or a records commit in
    the scan rows the merges read) lands nothing of the train: each part merges alone, as before."""
    w = tw
    if what == "plain":
        during = (f"[ -f {w['tmp']}/once ] || {{ touch {w['tmp']}/once; echo n > other.txt; git add other.txt; "
                  "git commit -qm 'not a records commit'; }")
    else:
        during = records_during(w, f"{V062}/scan_rows/X9.tsv")
    p, runs = train(w, "S1", "T2", during=during)
    t = trains(w)[-1]
    assert t["result"] == "each alone" and "main moved" in t["why"] and words in t["why"], (t, p.stdout + p.stderr)
    assert all("train" not in (merged(w, s) or {}) for s in ("S1", "T2")), (merged(w, "S1"), merged(w, "T2"))
    assert refusals(w) == []


def test_with_the_switch_off_a_train_is_refused_and_nothing_changes(tw):
    w = tw
    (w["data"] / "merge_train").write_text("yes\n")
    before = main_sha(w)
    p, runs = train(w, "S1", "T2")
    assert p.returncode == 1 and "merge train is off" in p.stderr and runs == 0, p.stderr
    assert main_sha(w) == before and trains(w) == []


@pytest.mark.parametrize("ids,words", [
    (["S1"], "2 to 3 different parts"), (["S1", "T2", "T3", "S2"], "2 to 3 different parts"),
    (["S1", "S1"], "2 to 3 different parts"), (["S1", "S2"], "S2 is not verified")])
def test_a_train_is_two_or_three_verified_parts(tw, ids, words):
    w = tw
    before = main_sha(w)
    p, runs = train(w, *ids)
    assert p.returncode == 1 and words in p.stderr and runs == 0, p.stderr
    assert main_sha(w) == before


def test_a_train_holds_each_of_its_parts_against_resume(tw):
    """While a train runs, resume.py refuses an action on any of its parts, and lets one on another part go on."""
    w = tw
    code = (f"import sys, json, subprocess; sys.path.insert(0, {str(w['lines'])!r}); import merge_slice as m, common as c\n"
            "fh = m.lock()\n"
            "c.write_json(c.DATA / m.RUNNING, {'slice': 'S1+T2', 'train': ['S1', 'T2']})\n"
            "out = {}\n"
            "for sid in ('T2', 'T3'):\n"
            "    p = subprocess.run([sys.executable, sys.argv[1], sid, 'send-back'], capture_output=True, text=True)\n"
            "    out[sid] = p.stdout + p.stderr\n"
            "print(json.dumps({'merging': m.merging(), **out}))\n")
    got = json.loads(sh([w["py"], "-c", code, str(w["lines"] / "resume.py")], w["repo"], w["env"]).stdout)
    assert got["merging"] == "S1+T2", got
    assert "a train of S1+T2" in got["T2"] and "waits for it" in got["T2"], got
    assert "waits for it" not in got["T3"], got


def test_while_the_train_s_gate_runs_the_running_record_names_all_its_parts(tw):
    w = tw
    seen = w["tmp"] / "merging.txt"
    during = (f"{w['py']} -c \"import sys; sys.path.insert(0, '{w['lines']}'); import merge_slice as m; "
              f"print(m.merging())\" >> {seen}")
    p, runs = train(w, "S1", "T2", "T3", during=during)
    assert p.returncode == 0 and seen.read_text().split() == ["S1+T2+T3"], (p.stderr, seen.read_text())


def test_a_train_waits_for_no_one_another_merge_running_refuses_it(tw):
    w = tw
    code = (f"import sys, json, subprocess; sys.path.insert(0, {str(w['lines'])!r}); import merge_slice as m\n"
            "fh = m.lock()\n"
            "p = subprocess.run([sys.executable, sys.argv[1], 'train', 'S1', 'T2'], capture_output=True, text=True)\n"
            "print(json.dumps([p.returncode, p.stderr]))\n")
    rc, err = json.loads(sh([w["py"], "-c", code, str(w["lines"] / "merge_slice.py")], w["repo"], w["env"]).stdout)
    assert rc == 1 and "another merge is running" in err and trains(w) == [], err
