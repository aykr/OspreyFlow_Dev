"""The standing accept applied before another round (LINE_FIXES_5_BRIEF.md, 3).

run_seat.py reads the verifier's record and, when its findings are only gaps in a test and the slice is at or past the
owner's standing round, accepts narrower at once and starts no builder round. On 21 November it did not for PL4d2: its
round-3 record (gaps only, 00:34 UTC) came while LR1's merge ran (00:21 to 00:53), the accept was refused by the merge
lock, and a fourth round was spent. Item 2 lets an accept go on while another slice merges; this holds the whole rule
at the verifier's record. A fault in behaviour, a fault and a gap, and any finding naming a key, a credential or a
security rule are never covered: those go round (or stop) as before.
"""
from __future__ import annotations

import fcntl
import json

import pytest

from test_accept import rec, state
from test_finding_kind import FAULT, GAP, at_verifier, finding, run_verifier
from test_gates import world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
ON = "accept-test-gaps\tfrom-round\t3\t2026-11-19\n"
GAPS = [finding(GAP, "no test fails if the loading message is dropped")]


def at_round(w, n, findings, merging=None):
    (w["repo"] / V062 / "standing.tsv").write_text(ON)
    wt, tip = at_verifier(w, round_=n, limit=8)  # the balanced dial's 8 rounds: far from the limit
    if merging is None:
        return tip, run_verifier(w, tip, findings)[0]
    (w["data"] / "merge.running.json").write_text(json.dumps({"slice": merging, "pid": 1}))
    with (w["data"] / "merge.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)  # a merge of another slice holds the lock, as LR1's did
        p = run_verifier(w, tip, findings)[0]
    return tip, p


def accepted(w, tip, n):
    st = state(w)
    return (st["phase"] == "verified" and st.get("accepted") is True and st["round"] == n
            and (rec(w) / f"accepted-{tip}.json").exists())


def went_round(w, tip, n):
    st = state(w)
    return st["phase"] == "building" and st["round"] == n + 1 and not (rec(w) / f"accepted-{tip}.json").exists()


def test_gaps_only_at_round_3_are_accepted_with_no_round(world):
    w = world
    tip, p = at_round(w, 3, GAPS)
    assert accepted(w, tip, 3), (state(w), p)


def test_gaps_only_at_round_3_while_another_slice_merges_are_accepted_with_no_round(world):
    """PL4d2's case of 21 November."""
    w = world
    tip, p = at_round(w, 3, GAPS, merging="LR1")
    assert accepted(w, tip, 3), (state(w), p)


def test_gaps_only_at_round_2_go_round(world):
    w = world
    tip, p = at_round(w, 2, GAPS)
    assert went_round(w, tip, 2), (state(w), p)


def test_a_fault_and_a_gap_go_round(world):
    w = world
    tip, p = at_round(w, 3, [finding(FAULT, "the count is wrong after a reload"), *GAPS])
    assert went_round(w, tip, 3), (state(w), p)


@pytest.mark.parametrize("what", ["no test fails if the API key is written to the log",
                                  "the credential check has no test for an expired one",
                                  "nothing tests that the guard's security rule refuses a push"],
                         ids=["key", "credential", "security-rule"])
def test_a_security_or_key_finding_is_never_accepted_on_the_standing_word(world, what):
    w = world
    tip, p = at_round(w, 3, [finding(GAP, what)])
    assert went_round(w, tip, 3), (state(w), p)
