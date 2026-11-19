"""The standing accept (RULINGS.md, 19 November 2026, ruling 5; ACCEPT_STEP_BRIEF.md, "The standing mode"; the owner's
order of 19 November): with the owner's one line in standing.tsv, a file only the owner can write, a slice at its third round or later whose newest verifier record holds only gaps in a
test, and no fault in behaviour, is accepted without a line per slice; each gap is written to the merge record for the
conductor's backlog row. A fault in behaviour, or a finding with no kind, is never accepted so. Off by default.

The verifier runs as run_seat.py runs it (its session stood in: test_finding_kind.run_verifier); resume.py, the merge
script and the guard run as the conductor and the hooks run them.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from test_accept import changes, rec, resume, said_refused, snapshot, state
from test_finding_kind import FAULT, GAP, at_verifier, finding, run_verifier
from test_gates import SRC, bash, guard, main_sha, merge, refused, sh, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
SWITCH = f"{V062}/standing.tsv"
ON = "accept-test-gaps\tfrom-round\t3\t2026-11-19\n"
GAPS = [finding(GAP, "no test fails if the loading message is dropped"),
        finding(GAP, "the late-load case is asserted by a snapshot only")]


def switch(w, body):
    f = w["repo"] / SWITCH
    if body is None:
        f.unlink(missing_ok=True)
    else:
        f.write_text(body)


def verified_round(w, findings, round_=3, limit=3, body=ON):
    switch(w, body)
    wt, tip = at_verifier(w, round_=round_, limit=limit)
    p, _ = run_verifier(w, tip, findings)
    return wt, tip, p


def not_accepted(w, tip):
    st = state(w)
    return (st["phase"] in ("stopped", "building") and not st.get("accepted")
            and not (rec(w) / f"accepted-{tip}.json").exists()
            and not any(r[2] == "accept" for r in changes(w)))


@pytest.mark.parametrize("body", [None, "", "# accept-test-gaps from-round 3 2026-11-19\n",
                                  "accept-test-gaps from-round 3\n", "accept-test-gaps from-round three 2026-11-19\n",
                                  "accept-test-gaps from-round 2 2026-11-19\n", "accept-test-gap from-round 3 2026-11-19\n",
                                  "accept-test-gaps from-round 3 2026-11-31\n", ON + ON],
                         ids=["missing", "empty", "a-comment", "no-date", "a-word", "below-the-third-round", "misspelt",
                              "no-such-date", "twice"])
def test_standing_accept_off_or_unclear_accepts_nothing(world, body):
    w = world
    wt, tip, p = verified_round(w, GAPS, body=body)
    assert not_accepted(w, tip), (state(w), p.stdout, p.stderr)
    assert state(w)["phase"] == "stopped"                                  # stopped at its limit, as before


def test_standing_accept_on_accepts_a_third_round_of_gaps_only_and_the_merge_lists_each_gap(world):
    w = world
    wt, tip, p = verified_round(w, GAPS)
    st = state(w)
    assert st["phase"] == "verified" and st["accepted"] is True and st["tip"] == tip, (st, p.stdout, p.stderr)
    assert not (w["repo"] / V062 / "resume.tsv").exists()                   # no line from the owner per slice
    a = json.loads((rec(w) / f"accepted-{tip}.json").read_text())
    assert a["findings"] == GAPS and a["gaps_in_a_test"] == GAPS and a["faults_in_behaviour"] == [] == a["no_kind"]
    assert a["by"] == "standing" and "accept-test-gaps from-round 3 2026-11-19" in a["rule"] and a["round"] == 3
    log = [r for r in changes(w) if r[2] == "accept"]
    assert len(log) == 1 and tip in log[0][3] and "standing" in log[0][3], changes(w)
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    done = json.loads((rec(w) / "merged.json").read_text())
    af = done["accepted_findings"]
    assert af["standing"] is True and af["backlog_rows"] == GAPS and "accept-test-gaps" in af["rule"], af        # each gap, for the conductor's backlog row
    board = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    assert "merged, accepted narrower: 2 findings" in board.stdout and "2 gaps in a test for the backlog" in board.stdout, \
        board.stdout + board.stderr


def test_standing_accept_waits_for_the_third_round(world):
    w = world
    wt, tip, p = verified_round(w, GAPS, round_=2, limit=2)
    assert not_accepted(w, tip), (state(w), p.stdout)


@pytest.mark.parametrize("extra", [finding(FAULT, "the form shows a choice before its data has loaded"),
                                   finding(None, "a finding the verifier gave no kind"),
                                   finding("a nit", "a finding of another kind")],
                         ids=["a-fault-in-behaviour", "no-kind", "another-kind"])
def test_standing_accept_never_accepts_a_fault_in_behaviour_or_a_finding_with_no_kind(world, extra):
    w = world
    wt, tip, p = verified_round(w, [*GAPS, extra])
    assert not_accepted(w, tip), (state(w), p.stdout)
    before = snapshot(w)
    p = resume(w)                                                             # nor when the conductor asks
    assert said_refused(p), p.stdout + p.stderr
    assert snapshot(w) == before


def test_standing_accept_by_the_conductor_for_a_slice_already_stopped_and_not_past_a_newer_record(world):
    """A slice stopped at round 3 before the switch was on: the conductor runs resume.py accept, with no line. A record
    newer than the verifier's (the merge gate's) holds findings with no kind, so it is refused while that is newest."""
    w = world
    wt, tip, p = verified_round(w, GAPS, body=None)
    assert state(w)["phase"] == "stopped"
    switch(w, ON)
    gate = rec(w) / f"verify-gate-{tip}.json"
    gate.write_text(json.dumps({"slice": "S1", "commit": tip, "verdict": "findings", "passes": [],
                                "findings": [{"file": "", "what": "the full gate was red", "evidence": "log"}]}))
    later = time.time() + 5
    os.utime(gate, (later, later))
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "newest"), p.stderr
    assert snapshot(w) == before
    gate.unlink()
    p = resume(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert state(w)["phase"] == "verified" and (rec(w) / f"accepted-{tip}.json").exists()


def test_standing_accept_switch_is_the_owners_alone(world):
    w = world
    f = w["repo"] / SWITCH
    for seat in (None, "conductor", "builder", "verifier", "scout"):
        kw = {"seat": seat} if seat else {}
        if seat == "builder":
            kw["wt"] = w["repo"]
        assert refused(guard(w, "Write", {"file_path": str(f), "content": ON}, **kw)), seat
        assert refused(guard(w, "Edit", {"file_path": str(f), "old_string": "3", "new_string": "1"}, **kw)), seat
        assert refused(bash(w, f"printf 'accept-test-gaps from-round 3 2026-11-19\\n' > {SWITCH}", **kw)), seat
    switch(w, ON)
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "records", "-m", "docs: on", SWITCH], w["repo"], w["env"],
           check=False)
    assert p.returncode == 1 and "owner's file" in p.stderr, p.stderr


def test_standing_accept_switch_on_a_slices_branch_is_a_protected_path(world):
    from test_gates import built, verified
    w = world
    wt, tip = built(w, extra={SWITCH: ON})
    verified(w, wt, tip)
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "protected paths" in p.stderr and SWITCH in p.stderr and main_sha(w) == before


def test_standing_accept_merge_reads_the_owners_line_again(world):
    """The line taken away between the acceptance and the merge: the merge is refused."""
    w = world
    wt, tip, p = verified_round(w, GAPS)
    assert state(w)["phase"] == "verified", p.stdout
    switch(w, None)
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "standing word" in p.stderr and main_sha(w) == before, p.stderr


@pytest.mark.parametrize("prefixed, taken", [(["GAP IN A TEST: the printed line is pinned by no test"], True),
                                             (["GAP IN A TEST: a", "FAULT IN BEHAVIOUR: b"], False),
                                             (["the printed line is pinned by no test"], False)],
                         ids=["gaps-only", "a-fault", "unmarked"])
def test_standing_accept_reads_a_record_written_before_the_kind_field_by_its_prefixes(world, prefixed, taken):
    """GG6 (round 4 of 4) and BL6 (round 5 of 5), each stopped with one test gap in a record from before the field."""
    w = world
    wt, tip, p = verified_round(w, GAPS, round_=4, limit=4, body=None)
    assert state(w)["phase"] == "stopped"
    vf = rec(w) / f"verify-{tip}.json"
    v = json.loads(vf.read_text())
    v.pop("kinds")
    v["findings"] = [{"what": x, "evidence": "e", "file": "a.py"} for x in prefixed]
    for ps in v["passes"]:
        ps["findings"] = v["findings"]
    vf.write_text(json.dumps(v))
    switch(w, ON)
    p = resume(w)
    if taken:
        assert p.returncode == 0, p.stdout + p.stderr
        a = json.loads((rec(w) / f"accepted-{tip}.json").read_text())
        assert a["by"] == "standing" and a["gaps_in_a_test"] == v["findings"]
        assert merge(w).returncode == 0
    else:
        assert said_refused(p, "not only gaps"), p.stdout + p.stderr
        assert not (rec(w) / f"accepted-{tip}.json").exists()
