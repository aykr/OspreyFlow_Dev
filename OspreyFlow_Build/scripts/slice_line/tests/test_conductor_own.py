"""The conductor's own word for five actions (the owner, 24 November 2026: "cut my paperwork"; his answers the same day).

`resume.py <ID> <action> --own "<reason>"` stands in for the owner's resume.tsv line for retire (a part another has
replaced), send-back (a verified part the merge gate refused by its own test, once a tip), add-round (no further than
the highest rounds limit the dial gives), move-seat (to an account accounts.yaml names, while no seat of the part runs)
and clear-stop (only for a cause self-clear proves the line's). Each use is logged in owner-changes.tsv with its reason
("conductor (own, <date>, use N of 20) ...") and shown on the board (self-clears.tsv, cause "own"). Twenty a day across
them; at the budget it stops for the owner. Never for a part whose open findings or stop name a key, a credential or a
security rule, nor for a part the owner has parked. resume.tsv stays the owner's: the guard refuses the conductor every
line in it, and resume.py refuses --own for every other action. A merge rerun of a refused tip is the conductor's,
logged and shown, and uses none of the budget.
"""
from __future__ import annotations

import json

import pytest

from test_gates import TODAY, bash, built, guard, merge, refused, sh, started, verified, world  # noqa: F401
from test_resume import V062, at_limit, changes, owner_line, red_stopped, said_refused, set_state, snapshot, state

OWN_FILE = "OspreyFlow_Build/tests/test_s1_own.py"


def own(w, action, reason, *args, slice_id="S1"):
    return sh([w["py"], str(w["lines"] / "resume.py"), slice_id, action, *args, "--own", reason], w["repo"], w["env"],
              check=False)


def rows(w, slice_id="S1"):
    rec = w["data"] / f"records/{slice_id}"
    (rec).mkdir(parents=True, exist_ok=True)
    return rec


def clears(w):
    f = w["data"] / "self-clears.tsv"
    return [dict(zip(f.read_text().splitlines()[0].split("\t"), ln.split("\t")))
            for ln in f.read_text().splitlines()[1:]] if f.exists() else []


def at_limit_3(w):
    """at_limit, at a rounds limit of 3 (the world's dial is balanced, whose 8 is the highest: no room above it)."""
    wt = at_limit(w)
    set_state(w, round=3, rounds_limit=3)
    return wt


def own_rows(w):
    return [r for r in changes(w) if r[3].startswith("conductor (own")]


def slices(w, *ids):
    """Rows for more parts in slices.tsv on main (S1's row is the world's own)."""
    f = w["repo"] / V062 / "slices.tsv"
    head, *body = f.read_text().splitlines()
    s1 = next(ln for ln in body if ln.startswith("S1\t"))
    f.write_text("\n".join([head, *body, *(s1.replace("S1\t", f"{i}\t", 1) for i in ids)]) + "\n")
    sh(["git", "add", "--", str(f)], w["repo"], w["env"])
    sh(["git", "commit", "-qm", "docs: more rows"], w["repo"], w["env"])


def refused_by_own_test(w, at_the_limit=True):
    """S1 verified, then refused by the full gate on its own test (a file its branch adds), at its rounds limit."""
    wt, tip = built(w, extra={OWN_FILE: "def test_s1():\n    assert True\n"})
    verified(w, wt, tip)
    limit = 3                                                   # below the dial's highest (8): room for one more
    set_state(w, phase="verified", tip=tip)
    rec = w["data"] / "records/S1"
    (rec / f"verify-gate-{tip}.json").write_text(json.dumps({
        "slice": "S1", "commit": tip, "verdict": "findings", "passes": [],
        "findings": [{"file": OWN_FILE, "what": "The merge gate's full run failed it: E assert False", "evidence": "x"}]}))
    set_state(w, phase="refused", refused_for="gate", refused_tests=1, refused_at="2026-11-24T10:00:00Z",
              round=limit if at_the_limit else 1, rounds_limit=limit, note="refused by the gate: 1 tests")
    return wt, tip


# ------------------------------------------------------------------ only the five, and resume.tsv stays the owner's


@pytest.mark.parametrize("action", ["refreeze", "accept", "correct-command", "undo-seat-failure", "self-clear"])
def test_the_conductors_own_word_is_refused_for_every_other_action(world, action):
    w = world
    at_limit(w)
    before = snapshot(w)
    p = own(w, action, "the conductor's reason")
    assert said_refused(p, "alone", "the owner's resume.tsv line"), p.stdout + p.stderr
    assert snapshot(w) == before and changes(w) == []


@pytest.mark.parametrize("action", ["retire", "send-back", "add-round", "move-seat builder sol", "clear-stop", "refreeze",
                                    "accept", "park"])
def test_the_guard_still_refuses_the_conductor_every_line_in_resume_tsv(world, action):
    w = world
    f = w["repo"] / V062 / "resume.tsv"
    line = f"S1\t{action.replace(' ', chr(9))}\t{TODAY}\n"
    assert refused(guard(w, "Write", {"file_path": str(f), "content": line}, seat="conductor"))
    assert refused(guard(w, "Edit", {"file_path": str(f), "old_string": "a", "new_string": line}, seat="conductor"))
    assert refused(bash(w, f"printf '{line.encode('unicode_escape').decode()}' >> {V062}/resume.tsv", seat="conductor"))
    assert refused(bash(w, f"printf 'clear-line-stops\\tper-day\\t10\\t{TODAY}\\n' >> {V062}/standing.tsv",
                        seat="conductor"))


def test_the_guard_lets_the_conductor_run_resume_with_its_own_word(world):
    w = world
    p = bash(w, "OspreyFlow_Build/scripts/slice_line/resume.py S1 retire --own 'replaced by S2'", seat="conductor")
    assert not refused(p), p.stderr


def test_the_conductors_own_word_needs_a_reason(world):
    w = world
    at_limit(w)
    p = own(w, "add-round", "  ")
    assert said_refused(p, "needs its reason"), p.stdout + p.stderr


# ------------------------------------------------------------------ retire: a part another has replaced


def test_retire_on_the_conductors_word_for_a_part_another_has_replaced(world):
    w = world
    slices(w, "S2")
    p = own(w, "retire", "replaced by S2 (it carries the same screen)")
    assert p.returncode == 0, p.stdout + p.stderr
    assert (w["data"] / "records/S1/retired.json").exists()
    (row,) = own_rows(w)
    assert row[2] == "retire" and "use 1 of 20" in row[3] and "replaced by S2" in row[3], row
    (shown,) = clears(w)
    assert (shown["slice"], shown["stop"], shown["cause"]) == ("S1", "retire", "own") and "replaced by S2" in shown["what"]


@pytest.mark.parametrize("reason,why", [("it is old", "replaced by <ID>"), ("replaced by S1", "replaced by <ID>"),
                                        ("replaced by S9", "no row")], ids=["no-replacement", "itself", "no-such-part"])
def test_retire_on_the_conductors_word_needs_the_part_that_replaced_it(world, reason, why):
    w = world
    p = own(w, "retire", reason)
    assert said_refused(p, why), p.stdout + p.stderr
    assert not (w["data"] / "records/S1/retired.json").exists() and changes(w) == []


# ------------------------------------------------------------------ send-back: refused by its own test, once a tip


def test_send_back_on_the_conductors_word_for_a_part_refused_by_its_own_test_at_its_limit(world):
    w = world
    wt, tip = refused_by_own_test(w)
    limit = state(w)["rounds_limit"]
    p = own(w, "send-back", "its own test failed in the full gate")
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert st["phase"] == "building" and st["round"] == limit + 1 and st["rounds_limit"] == limit + 1, st
    (row,) = own_rows(w)
    assert f"send-back at {tip[:10]}" in row[3], row


def test_send_back_on_the_conductors_word_is_once_a_tip(world):
    w = world
    wt, tip = refused_by_own_test(w)
    assert own(w, "send-back", "first").returncode == 0
    st = state(w)
    set_state(w, phase="refused", refused_for="gate", round=st["rounds_limit"], tip=tip)
    p = own(w, "send-back", "again")
    assert said_refused(p, "once a tip"), p.stdout + p.stderr


def test_send_back_on_the_conductors_word_is_refused_for_a_test_not_its_own(world):
    w = world
    wt, tip = refused_by_own_test(w)
    gate = w["data"] / f"records/S1/verify-gate-{tip}.json"
    g = json.loads(gate.read_text())
    g["findings"][0]["file"] = "OspreyFlow_Build/tests/glass_trees/test_pl4d3d_declared_units.py"
    gate.write_text(json.dumps(g))
    p = own(w, "send-back", "a race")
    assert said_refused(p, "not its own", "reruns the merge"), p.stdout + p.stderr
    assert own_rows(w) == []


def test_send_back_on_the_conductors_word_is_refused_for_a_verified_part(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    p = own(w, "send-back", "a finding")
    assert said_refused(p, "refused by its own test"), p.stdout + p.stderr


# ------------------------------------------------------------------ add-round: up to the dial's highest limit


def test_add_round_on_the_conductors_word_within_the_dials_highest_limit(world):
    w = world
    at_limit_3(w)
    rnd = state(w)["round"]
    p = own(w, "add-round", "one more for the last finding")
    assert p.returncode == 0, p.stdout + p.stderr
    assert state(w)["round"] == rnd + 1
    assert len(own_rows(w)) == 1


def test_add_round_on_the_conductors_word_past_the_dials_highest_limit_is_the_owners(world):
    w = world
    at_limit(w)
    most = max(v["rounds"] for v in __import__("yaml").safe_load((w["repo"] / V062 / "dial.yaml").read_text())["settings"].values())
    set_state(w, round=most, rounds_limit=most)
    p = own(w, "add-round", "one more")
    assert said_refused(p, "past the highest rounds limit the dial gives"), p.stdout + p.stderr


# ------------------------------------------------------------------ move-seat


def test_move_seat_on_the_conductors_word(world):
    w = world
    p0, wt = started(w)
    assert p0.returncode == 0
    acct = (w["repo"] / V062 / "accounts.yaml")
    to = "sol" if state(w).get("account") != "sol" else "default"
    p = own(w, "move-seat", "the account is at its limit", "builder", to)
    assert p.returncode == 0, p.stdout + p.stderr
    assert state(w)["account"] == to and len(own_rows(w)) == 1 and acct.exists()


def test_move_seat_on_the_conductors_word_to_an_account_not_named_is_refused(world):
    w = world
    started(w)
    p = own(w, "move-seat", "x", "builder", "nobody")
    assert said_refused(p, "not an account"), p.stdout + p.stderr
    assert own_rows(w) == []


# ------------------------------------------------------------------ clear-stop: only self-clear's proven causes


def test_clear_stop_on_the_conductors_word_is_refused_for_a_red_of_the_parts_own(world):
    """A red in the part's own acceptance is never the line's cause (self-clear's own rule): the owner's."""
    w = world
    red_stopped(w)
    before = snapshot(w)
    p = own(w, "clear-stop", "looks flaky")
    assert said_refused(p), p.stdout + p.stderr
    assert snapshot(w) == before and own_rows(w) == []


def test_clear_stop_on_the_conductors_word_needs_no_standing_permission(world):
    """Self-clear's cause (a), main moved under the part: cleared on the conductor's own word, with no standing.tsv at
    all, logged on its budget and shown on the board."""
    from test_self_clear import red_on_mains_check
    w = world
    assert not (w["repo"] / V062 / "standing.tsv").exists()
    red_on_mains_check(w)
    p = own(w, "clear-stop", "main fixed the check under it")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "cleared by the line (cause a)" in p.stdout and "on the conductor's own word" in p.stdout, p.stdout
    assert state(w)["phase"] == "building"
    (row,) = own_rows(w)
    assert row[2] == "clear-stop" and "cause a" in row[3], row
    assert [r["cause"] for r in clears(w)] == ["own"]


# ------------------------------------------------------------------ the budget, the words, the park


def test_at_twenty_a_day_the_conductors_word_stops_for_the_owner(world):
    w = world
    at_limit_3(w)
    f = w["data"] / "owner-changes.tsv"
    f.write_text("at\tslice\taction\tdetail\n" + "".join(
        f"{TODAY}T0{i % 10}:00:00Z\tS9\tadd-round\tconductor (own, {TODAY}, use {i + 1} of 20) add-round (x): done\n"
        for i in range(20)))
    p = own(w, "add-round", "one more")
    assert said_refused(p, "given its 20 for today", "stops for the owner"), p.stdout + p.stderr


def test_yesterdays_uses_do_not_count(world):
    w = world
    at_limit_3(w)
    f = w["data"] / "owner-changes.tsv"
    f.write_text("at\tslice\taction\tdetail\n" + "".join(
        f"2020-01-01T00:00:00Z\tS9\tadd-round\tconductor (own, 2020-01-01, use {i + 1} of 20) add-round (x): done\n"
        for i in range(20)))
    assert own(w, "add-round", "one more").returncode == 0


@pytest.mark.parametrize("what,stops", [("the API key is shown back", True), ("an analyst's key press is lost", False)],
                         ids=["api-key", "key-press"])
def test_never_for_a_part_whose_open_findings_name_a_key(world, what, stops):
    w = world
    at_limit_3(w)
    st = state(w)
    tip = sh("git rev-parse lane/slice-S1", w["repo"]).stdout.strip()
    set_state(w, tip=tip)
    (w["data"] / f"records/S1/verify-{tip}.json").write_text(json.dumps(
        {"slice": "S1", "commit": tip, "verdict": "findings", "findings": [{"file": "x.py", "what": what}]}))
    p = own(w, "add-round", "one more")
    if stops:
        assert said_refused(p, "key, a credential or a security rule"), p.stdout + p.stderr
    else:
        assert p.returncode == 0, p.stdout + p.stderr
    assert state(w)["round"] == st["round"] + (0 if stops else 1)


def test_never_for_a_part_the_owner_has_parked(world):
    w = world
    at_limit_3(w)
    owner_line(w, f"S1\tpark\t{TODAY}")
    p = own(w, "add-round", "one more")
    assert said_refused(p, "parked"), p.stdout + p.stderr


# ------------------------------------------------------------------ a merge rerun: logged and shown, no budget


def test_a_merge_rerun_of_a_refused_tip_is_logged_and_shown_and_uses_no_budget(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    (w["data"] / "refusals.tsv").write_text(f"at\tslice\ttip\tcause\n2026-11-24T10:00:00Z\tS1\t{tip}\tthe full gate: test\n")
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    reruns = [r for r in changes(w) if r[2] == "merge-rerun"]
    assert len(reruns) == 1 and tip[:10] in reruns[0][3] and not reruns[0][3].startswith("conductor (own"), reruns
    assert own_rows(w) == []
    assert [r["cause"] for r in clears(w)] == ["rerun"]


def test_a_first_merge_logs_no_rerun(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    assert merge(w).returncode == 0
    assert [r for r in changes(w) if r[2] == "merge-rerun"] == []


def test_a_refusal_of_another_tip_logs_no_rerun(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    (w["data"] / "refusals.tsv").write_text(f"at\tslice\ttip\tcause\n2026-11-24T10:00:00Z\tS1\t{'0' * 40}\tthe full gate: test\n")
    assert merge(w).returncode == 0
    assert [r for r in changes(w) if r[2] == "merge-rerun"] == []
