"""Line fault 17 (the owner's file 008, 22 November 2026; SE6b): a merge refused because the slice's acceptance or checks
are red on the merge result (main with the slice merged in) left the slice at `verified`, so send-back ("not refused by
the merge gate"), add-round ("not stopped at its rounds limit") and every other action refused it, and no builder could
start. Now that refusal is recorded for the builder as a refusal at the full gate is (refused for `gate`, a findings
record), and resume.py send-back returns it to its builder.

SE6b's shape: the slice is verified; main then moves a path the slice's acceptance (or checks) reads.
"""
from __future__ import annotations

import json

import pytest

from test_gates import built, merge, sh, started, verified, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"


def state(w):
    return json.loads((w["data"] / "records/S1/state.json").read_text())


@pytest.mark.parametrize("which", ["acceptance", "checks"])
def test_red_on_the_merge_result_is_recorded_and_send_back_returns_the_slice(world, which):
    w = world
    (w["repo"] / "lib").mkdir()
    (w["repo"] / "lib/thing.txt").write_text("thing\n")
    if which == "checks":  # the slice's frozen checks read the path
        tsv = w["repo"] / V062 / "slices.tsv"
        tsv.write_text(tsv.read_text().replace("sh accept.sh\ttrue", "sh accept.sh\ttest -f lib/thing.txt"))
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'lib'", w["repo"], w["env"])
    accept = "test -f feature.txt" + (" && test -f lib/thing.txt" if which == "acceptance" else "")
    wt, tip = built(w, accept=accept)
    verified(w, wt, tip)
    f = w["data"] / "records/S1/state.json"
    f.write_text(json.dumps({**json.loads(f.read_text()), "phase": "verified", "tip": tip}))  # as SE6b was
    sh("git mv lib/thing.txt lib/moved.txt && git commit -qm 'refactor: the path moves'", w["repo"], w["env"])  # PL4d3e
    before = sh("git rev-parse main", w["repo"]).stdout.strip()
    p = merge(w)
    assert p.returncode == 1 and f"{which} is red on the merge result" in p.stderr, p.stderr
    r = sh([w["py"], str(w["lines"] / "resume.py"), "S1", "add-round"], w["repo"], w["env"], check=False)
    assert r.returncode == 1                                    # (no add-round line: refused as before, nothing changed)
    assert "send-back" in p.stderr and sh("git rev-parse main", w["repo"]).stdout.strip() == before
    st = state(w)
    assert (st["phase"], st["refused_for"]) == ("refused", "gate"), st
    rec = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())
    assert rec["verdict"] == "findings" and rec["commit"] == tip and rec["findings"], rec
    assert which in rec["note"], rec
    assert f"The slice's {which} command is red on the merge result" in rec["findings"][0]["what"], rec  # the builder's words
    r = sh([w["py"], str(w["lines"] / "resume.py"), "S1", "send-back"], w["repo"], w["env"], check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert state(w)["phase"] == "building", state(w)
