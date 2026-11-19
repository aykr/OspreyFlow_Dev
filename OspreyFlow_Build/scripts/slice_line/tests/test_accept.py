"""The accept step (slice-line/proposals/ACCEPT_STEP_BRIEF.md): a slice stopped at its rounds limit with findings is
merged narrower on the owner's written word, for the exact tip a verifier saw, through every other gate.

The slice is stopped as the line stops it: built green (the Stop hook's test record), then run_seat.verifier with its
session stood in by a result line carrying findings (test_finding_kind.run_verifier), at the last round. resume.py
and merge_slice.py run as the conductor runs them.
"""
from __future__ import annotations

import fcntl
import json
import time

import pytest

from test_finding_kind import FAULT, GAP, at_verifier, finding, run_verifier
from test_gates import main_sha, merge, sh, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
TODAY = time.strftime("%Y-%m-%d", time.gmtime())
FINDINGS = [finding(FAULT, "the form shows a choice before its data has loaded"),
            finding(GAP, "no test fails if the error message is dropped")]


def resume(w, action="accept", slice_id="S1"):
    return sh([w["py"], str(w["lines"] / "resume.py"), slice_id, action], w["repo"], w["env"], check=False)


def said_refused(p, *words):
    out = p.stdout + p.stderr
    return (p.returncode == 1 and p.stderr.startswith("Refused: ") and "Traceback" not in out
            and all(x in p.stderr for x in words))


def owner_line(w, *lines):
    (w["repo"] / V062 / "resume.tsv").write_text("".join(f"{ln}\n" for ln in lines))


def rec(w):
    return w["data"] / "records/S1"


def state(w):
    return json.loads((rec(w) / "state.json").read_text())


def snapshot(w):
    return {str(p): p.read_bytes() for p in sorted((w["data"] / "records").rglob("*")) if p.is_file()}


def changes(w):
    f = w["data"] / "owner-changes.tsv"
    return [ln.split("\t") for ln in f.read_text().splitlines()[1:]] if f.exists() else []


def stopped_with_findings(w, findings=FINDINGS, round_=2, limit=2):
    """S1 stopped by its verifier's findings at its rounds limit, as run_seat.verifier stops it."""
    wt, tip = at_verifier(w, round_=round_, limit=limit)
    p, _ = run_verifier(w, tip, findings)
    assert state(w)["phase"] == ("stopped" if round_ >= limit else "building"), (state(w), p.stdout, p.stderr)
    return wt, tip


def accepted(w):
    wt, tip = stopped_with_findings(w)
    owner_line(w, f"S1\taccept\t{TODAY}")
    p = resume(w)
    assert p.returncode == 0, p.stdout + p.stderr
    return wt, tip


# ------------------------------------------------------------------ the owner's word, and only it


@pytest.mark.parametrize("line", [None, "S9\taccept\t@TODAY@", "S1\tadd-round\t@TODAY@", "S1\taccept\t2020-01-01"],
                         ids=["no-line", "another-slice", "another-action", "another-date"])
def test_accept_refuses_without_the_owners_line_and_writes_nothing(world, line):
    w = world
    wt, tip = stopped_with_findings(w)
    if line:
        owner_line(w, line.replace("@TODAY@", TODAY))
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "no line", "accept"), p.stdout + p.stderr
    assert snapshot(w) == before and not list(rec(w).glob("accepted-*.json")) and changes(w) == []


def test_accept_writes_the_acceptance_for_that_tip_and_changes_no_finding(world):
    w = world
    three = [*FINDINGS, finding(None, "a finding the verifier gave no kind")]
    wt, tip = stopped_with_findings(w, findings=three)
    verifier_record = (rec(w) / f"verify-{tip}.json").read_bytes()
    owner_line(w, f"S1\taccept\t{TODAY}")
    p = resume(w)
    assert p.returncode == 0, p.stdout + p.stderr
    a = json.loads((rec(w) / f"accepted-{tip}.json").read_text())
    assert a["tip"] == tip and a["line"] == f"S1 accept {TODAY}" and a["date"] == TODAY
    assert a["findings"] == three                                          # verbatim
    assert a["faults_in_behaviour"] == [three[0]] and a["gaps_in_a_test"] == [three[1]] and a["no_kind"] == [three[2]]
    assert (rec(w) / f"verify-{tip}.json").read_bytes() == verifier_record  # the verifier's record is untouched
    st = state(w)
    assert st["phase"] == "verified" and st["accepted"] is True and st["tip"] == tip
    log = changes(w)
    assert len(log) == 1 and log[0][1:3] == ["S1", "accept"] and tip in log[0][3] and "3 findings" in log[0][3], log


def test_accept_refuses_a_slice_whose_last_verdict_is_pass(world):
    w = world
    wt, tip = at_verifier(w, round_=2, limit=2)
    run_verifier(w, tip, [], verdict="pass")
    assert state(w)["phase"] == "verified"
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "nothing to accept"), p.stderr
    assert snapshot(w) == before and changes(w) == []


def test_accept_refuses_a_slice_not_stopped_at_its_rounds_limit(world):
    w = world
    stopped_with_findings(w, round_=1, limit=2)  # findings in round 1 of 2: back to the builder, not stopped
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "rounds limit"), p.stderr
    assert snapshot(w) == before


def test_accept_refuses_a_tip_the_verifier_did_not_see_or_with_no_green_test_record(world):
    w = world
    wt, tip = stopped_with_findings(w)
    (wt / "more.txt").write_text("after the verifier\n")
    sh("git add more.txt && git commit -qm 'feat: more'", wt, w["env"])
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "test record"), p.stderr                          # no Stop hook record for the new tip
    assert snapshot(w) == before
    from test_gates import stop_gate
    assert stop_gate(w, wt) is None                                          # green at the new tip: still unseen
    before = snapshot(w)
    p = resume(w)
    assert said_refused(p, "verifier"), p.stderr
    assert snapshot(w) == before and changes(w) == []


def test_accept_refuses_while_a_merge_runs_or_the_worktree_has_uncommitted_changes(world):
    w = world
    wt, tip = stopped_with_findings(w)
    owner_line(w, f"S1\taccept\t{TODAY}")
    before = snapshot(w)
    with (w["data"] / "merge.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        p = resume(w)
    assert said_refused(p, "another merge is running"), p.stderr
    (wt / "half-done.txt").write_text("x\n")
    p = resume(w)
    assert said_refused(p, "uncommitted"), p.stderr
    assert snapshot(w) == before and changes(w) == []


# ------------------------------------------------------------------ the merge takes the acceptance for that tip only


def test_accepted_merge_names_the_accepted_findings_and_the_board_shows_it(world):
    w = world
    wt, tip = accepted(w)
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    done = json.loads((rec(w) / "merged.json").read_text())
    assert main_sha(w) == done["merge"] and done["tip"] == tip
    af = done["accepted_findings"]
    assert af["count"] == 2 and af["findings"] == FINDINGS and af["gaps_in_a_test"] == [FINDINGS[1]], af
    assert af["record"] == f"accepted-{tip}.json" and af["line"] == f"S1 accept {TODAY}"
    board = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    assert "merged, accepted narrower: 2 findings" in board.stdout, board.stdout + board.stderr
    status = (w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js").read_text()
    co1 = json.loads(status.split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))["builds"]["CO1"]
    assert co1["state"] == "done" and "accepted narrower: 2 findings" in co1["note"], co1
    assert co1["accepted_findings"] == FINDINGS


def test_accepted_merge_is_refused_when_the_tip_moved_after_the_acceptance(world):
    w = world
    wt, tip = accepted(w)
    (wt / "more.txt").write_text("after the acceptance\n")
    sh("git add more.txt && git commit -qm 'feat: more'", wt, w["env"])
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "no verifier record" in p.stderr and main_sha(w) == before, p.stderr


@pytest.mark.parametrize("how", ["removed", "made-a-pass", "findings-changed", "another-commit"])
def test_accepted_merge_is_refused_without_the_verifiers_findings_record_behind_it(world, how):
    w = world
    wt, tip = accepted(w)
    vf = rec(w) / f"verify-{tip}.json"
    v = json.loads(vf.read_text())
    if how == "removed":
        vf.unlink()
    elif how == "made-a-pass":
        v["verdict"] = "pass"
        vf.write_text(json.dumps(v))
    elif how == "findings-changed":
        v["findings"] = v["findings"][1:]
        vf.write_text(json.dumps(v))
    else:
        v["commit"] = "0" * 40
        vf.write_text(json.dumps(v))
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and p.stderr.startswith("Refused: ") and main_sha(w) == before, p.stderr
    assert not (rec(w) / "merged.json").exists()


def test_accepted_merge_is_refused_for_an_acceptance_with_no_logged_use_of_the_owners_line(world):
    """An acceptance record nobody's resume.py wrote (no row in owner-changes.tsv for that slice and tip)."""
    w = world
    wt, tip = accepted(w)
    (w["data"] / "owner-changes.tsv").write_text("at\tslice\taction\tdetail\n")
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "owner-changes" in p.stderr and main_sha(w) == before, p.stderr


def test_accepted_merge_is_refused_when_the_full_gate_is_red(world):
    w = world
    accepted(w)
    before = main_sha(w)
    p = merge(w, gate="2")
    assert p.returncode == 1 and "full gate is red" in p.stderr and main_sha(w) == before, p.stderr
    assert not (rec(w) / "merged.json").exists()


def test_accepted_merge_still_needs_red_before(world):
    """The acceptance stands in for the verifier's pass only: an acceptance test that was never red still refuses."""
    w = world
    wt, tip = accepted(w)
    fz = rec(w) / "frozen.json"
    frozen = json.loads(fz.read_text())
    frozen["acceptance"] = "true"
    fz.write_text(json.dumps(frozen))
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("\tsh accept.sh\t", "\ttrue\t"))
    sh(f"git commit -qam 'docs: S1' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    p = merge(w)
    assert p.returncode == 1 and "never red" in p.stderr, p.stderr
