"""A verified slice goes back to its builder on the owner's own line (22 November 2026, SE9: a verifier's finding of a
gap in a test on an access-control path, which the owner does not accept narrower; a second verifier passed the same
tip, so the slice was verified and no action took it: send-back refused it as "not refused by the merge gate").

`resume.py <slice> send-back` now takes a verified slice too, only on the owner's line `<slice> send-back <date>` in
resume.tsv: one line, one use, logged. The round advances by one. The rounds limit is not raised by that line: past the
limit it needs the owner's add-round line as well, exactly as a refused slice's send-back does (both lines used, both
logged). The builder's prompt says why it is back, and the tip's pass is no longer the newest record.
"""
from __future__ import annotations

import json

from test_gates import TODAY, built, sh, verified, world  # noqa: F401  (world is a fixture)
from test_send_back import V062, resume, set_state, state


def a_verified_slice(w):
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    return wt, tip


def lines(w, *actions):
    (w["repo"] / V062 / "resume.tsv").write_text("".join(f"S1\t{a}\t{TODAY}\n" for a in actions))


def owner_rows(w):
    f = w["data"] / "owner-changes.tsv"
    return [ln for ln in f.read_text().splitlines()[1:] if ln.strip()] if f.exists() else []


def test_without_the_owners_line_a_verified_slice_is_refused_and_nothing_changes(world):
    w = world
    a_verified_slice(w)
    before = (w["data"] / "records/S1/state.json").read_bytes()
    p = resume(w, "send-back")
    assert p.returncode == 1 and p.stderr.startswith("Refused: "), p.stderr
    assert f"S1\tsend-back\t{TODAY}" in p.stderr, p.stderr          # it names the line that would do it
    assert (w["data"] / "records/S1/state.json").read_bytes() == before and not owner_rows(w)


def test_the_owners_line_sends_a_verified_slice_back_one_round_on_within_the_limit(world):
    w = world
    wt, tip = a_verified_slice(w)
    set_state(w, round=1, rounds_limit=3)
    lines(w, "send-back")
    p = resume(w, "send-back")
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert (st["phase"], st["round"], st["rounds_limit"]) == ("building", 2, 3), st
    rows = owner_rows(w)
    assert len(rows) == 1 and f"resume.tsv {TODAY} send-back: a verified slice sent back" in rows[0], rows
    rec = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())   # newer than the tip's pass
    assert rec["verdict"] == "findings" and rec["commit"] == tip and "the owner" in rec["findings"][0]["what"], rec
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import run_seat; print(run_seat.last_findings('S1'))")
    said = sh([w["py"], "-c", code], w["repo"], w["env"]).stdout
    assert "sent back by the owner" in said, said                  # the builder is told why it is back


def test_one_line_one_use(world):
    w = world
    wt, tip = a_verified_slice(w)
    set_state(w, round=1, rounds_limit=4)
    lines(w, "send-back")
    assert resume(w, "send-back").returncode == 0
    set_state(w, phase="verified", tip=tip)                          # verified again, the same day
    before = (w["data"] / "records/S1/state.json").read_bytes()
    p = resume(w, "send-back")
    assert p.returncode == 1 and "already used" in p.stderr, p.stderr
    assert (w["data"] / "records/S1/state.json").read_bytes() == before and len(owner_rows(w)) == 1


def test_past_the_limit_it_needs_the_add_round_line_too_and_uses_both(world):
    w = world
    a_verified_slice(w)
    set_state(w, round=3, rounds_limit=3)
    lines(w, "send-back")
    before = (w["data"] / "records/S1/state.json").read_bytes()
    p = resume(w, "send-back")
    assert p.returncode == 1 and f"S1\tadd-round\t{TODAY}" in p.stderr, p.stderr
    assert (w["data"] / "records/S1/state.json").read_bytes() == before and not owner_rows(w)   # the line is not used
    lines(w, "send-back", "add-round")
    p = resume(w, "send-back")
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert (st["phase"], st["round"], st["rounds_limit"]) == ("building", 4, 4), st
    rows = owner_rows(w)
    assert any(f"resume.tsv {TODAY} send-back:" in r for r in rows) and any(f"resume.tsv {TODAY} add-round:" in r
                                                                             for r in rows), rows
    set_state(w, phase="stopped", round=4, rounds_limit=4)          # the add-round line is spent: it cannot be used again
    p = sh([w["py"], str(w["lines"] / "resume.py"), "S1", "add-round"], w["repo"], w["env"], check=False)
    assert p.returncode == 1 and "already used" in p.stderr, p.stderr


def test_a_slice_neither_verified_nor_refused_is_still_refused_with_the_line(world):
    w = world
    a_verified_slice(w)
    set_state(w, phase="building")
    lines(w, "send-back")
    p = resume(w, "send-back")
    assert p.returncode == 1 and "phase building" in p.stderr, p.stderr
    assert not owner_rows(w)


def test_a_findings_record_already_at_the_tip_is_kept_beneath_the_owners(world):
    w = world
    wt, tip = a_verified_slice(w)
    set_state(w, round=1, rounds_limit=3)
    f = w["data"] / f"records/S1/verify-gate-{tip}.json"
    f.write_text(json.dumps({"slice": "S1", "commit": tip, "verdict": "findings", "findings": [{"what": "older"}]}))
    lines(w, "send-back")
    assert resume(w, "send-back").returncode == 0
    whats = [x["what"] for x in json.loads(f.read_text())["findings"]]
    assert len(whats) == 2 and "sent back by the owner" in whats[0] and whats[1] == "older", whats


def test_from_round_five_the_builder_is_pointed_at_its_rounds_table_and_told_when_it_is_missing(world):
    w = world
    wt, tip = a_verified_slice(w)
    set_state(w, round=6, rounds_limit=8)                           # SE9's own shape: round 6 of 8
    lines(w, "send-back")
    p = resume(w, "send-back")
    assert p.returncode == 0, p.stdout + p.stderr
    assert f"{V062}/slices/S1_ROUND7_TABLE.md is not on main yet" in p.stdout, p.stdout
    rec = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())
    assert "S1_ROUND7_TABLE.md" in rec["findings"][0]["what"], rec
    st = state(w)
    assert (st["phase"], st["round"], st["rounds_limit"]) == ("building", 7, 8), st
