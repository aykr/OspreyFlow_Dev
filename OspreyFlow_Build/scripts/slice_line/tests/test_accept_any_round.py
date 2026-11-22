"""The owner's accept at any round (the owner's word of 21 November 2026, seen on IS5a0 and PL11): his line
`<ID> accept <date>` applies as soon as the verifier's findings for the branch's tip are on record, whatever the round,
not only once the slice is stopped at its rounds limit. It never covers a finding that names a key, a credential or a
security rule, at any round (as the standing word, item 3; the owner's file 003).

It is refused, with nothing changed, when the builder has committed since the verifier's record (that tip was never
verified), when a seat of the slice is at work, when a newer record (the merge gate's) is the newest, and when the slice
is stopped on red checks. At the limit it takes any other finding as before.
"""
from __future__ import annotations

import json
import os

import pytest

from test_accept import FINDINGS, TODAY, changes, owner_line, rec, resume, said_refused, snapshot, state, \
    stopped_with_findings
from test_finding_kind import FAULT, GAP, finding
from test_gates import merge, sh, world  # noqa: F401  (world is a fixture)


def test_the_owners_accept_applies_in_round_1_once_the_verifiers_findings_are_on_record(world):
    w = world
    wt, tip = stopped_with_findings(w, round_=1, limit=3)       # findings in round 1 of 3: back to building
    assert state(w)["phase"] == "building" and state(w)["round"] == 2
    owner_line(w, f"S1\taccept\t{TODAY}")
    p = resume(w)
    assert p.returncode == 0, p.stdout + p.stderr
    a = json.loads((rec(w) / f"accepted-{tip}.json").read_text())
    assert a["tip"] == tip and a["findings"] == FINDINGS and a["line"] == f"S1 accept {TODAY}"
    assert a["round"] == 1 and a["before_the_limit"] is True, a
    st = state(w)
    assert st["phase"] == "verified" and st["accepted"] is True and st["tip"] == tip
    log = changes(w)
    assert len(log) == 1 and log[0][1:3] == ["S1", "accept"] and f"tip {tip}" in log[0][3] and "round 1 of 3" in log[0][3]
    p = merge(w)                                                  # the merge takes it, every other gate still runs
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads((rec(w) / "merged.json").read_text())["accepted_findings"]["count"] == 2


@pytest.mark.parametrize("what", ["the signing key is written to the log", "the session token survives a logout",
                                  "the security header is missing on the export route"],
                         ids=["key", "token", "security"])
def test_the_owners_accept_never_covers_a_security_or_key_finding_before_the_limit(world, what):
    w = world
    wt, tip = stopped_with_findings(w, findings=[finding(GAP, "no test for the empty list"), finding(FAULT, what)],
                                    round_=1, limit=3)
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "key, a credential or a security rule", "at any round"), p.stdout + p.stderr
    assert snapshot(w) == before and changes(w) == []
    assert not (rec(w) / f"accepted-{tip}.json").exists()


def test_the_owners_accept_at_the_limit_takes_any_other_finding_as_before(world):
    w = world
    wt, tip = stopped_with_findings(w)                            # a fault in behaviour and a gap, at round 2 of 2
    owner_line(w, f"S1\taccept\t{TODAY}")
    p = resume(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert state(w)["phase"] == "verified"
    a = json.loads((rec(w) / f"accepted-{tip}.json").read_text())
    assert "before_the_limit" not in a and "round" not in a, a      # the record at the limit is as it was


@pytest.mark.parametrize("what", ["the session token survives a logout", "the API key is shown back on the error page",
                                  "the signing secret is logged at debug level"], ids=["token", "key", "secret"])
def test_the_owners_accept_at_the_limit_never_covers_a_security_or_key_finding(world, what):
    """The owner's word of 21 November 2026 (his file 003): a fault that can expose a key, show it back, log it or send
    it where it was not given is never accepted, at any round, on the standing word or on his own line."""
    w = world
    wt, tip = stopped_with_findings(w, findings=[finding(GAP, "no test for the empty list"), finding(FAULT, what)])
    assert state(w)["phase"] == "stopped" and state(w)["round"] == state(w)["rounds_limit"]
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "key, a credential or a security rule", "at any round"), p.stdout + p.stderr
    assert snapshot(w) == before and changes(w) == []
    assert not (rec(w) / f"accepted-{tip}.json").exists()


def test_the_owners_accept_is_refused_when_the_builder_committed_after_the_verifiers_record(world):
    w = world
    wt, tip = stopped_with_findings(w, round_=1, limit=3)
    (wt / "OspreyFlow_Build/round2.txt").write_text("round 2\n")
    sh("git add -A && git commit -qm 'round 2'", wt, w["env"])
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "no green test record"), p.stdout + p.stderr
    assert snapshot(w) == before and changes(w) == []


@pytest.mark.parametrize("seat", ["builder", "verifier"])
def test_the_owners_accept_is_refused_while_a_seat_of_the_slice_is_at_work(world, seat):
    w = world
    wt, tip = stopped_with_findings(w, round_=1, limit=3)
    (rec(w) / f"running-{seat}.json").write_text(json.dumps({"slice": "S1", "seat": seat, "account": "a",
                                                             "pid": os.getpid(), "at": "now"}))
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, f"{seat} is at work"), p.stdout + p.stderr
    assert snapshot(w) == before and changes(w) == []


def test_the_owners_accept_before_the_limit_reads_only_the_newest_record(world):
    w = world
    wt, tip = stopped_with_findings(w, round_=1, limit=3)
    gate = rec(w) / f"verify-gate-{tip}.json"
    gate.write_text(json.dumps({"slice": "S1", "commit": tip, "verdict": "findings", "passes": [],
                                "findings": [{"file": "", "what": "the full gate was red", "evidence": "log"}]}))
    later = gate.stat().st_mtime + 5
    os.utime(gate, (later, later))
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "newest"), p.stdout + p.stderr
    assert snapshot(w) == before


def test_the_owners_accept_is_refused_for_a_slice_stopped_on_red_checks(world):
    w = world
    wt, tip = stopped_with_findings(w, round_=1, limit=3)
    st = state(w)
    st["phase"] = "stopped"
    (rec(w) / "state.json").write_text(json.dumps(st))
    (rec(w) / "red_stop.json").write_text(json.dumps({"slice": "S1", "red_stops": 6}))
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "red checks"), p.stdout + p.stderr
    assert snapshot(w) == before
