"""A builder that ends on a question is not "green; ready for the verifier" (the owner's word of 27 November 2026: the
conductor's line fault).

run_seat.py sent a part to its verifier whenever the tip had a green test record, whatever the builder's session ended
by saying. Two real endings, both green at their tips:
- GR1b, round 1: "Questions for the owner ... Should it (a) say "Select a dataset" instead, or (b) stay as it is?"
- CO3b, round 1: "**Question:** should I (a, recommended) ...; (b) ...; or (c, not advised) ...? ... The frozen
  acceptance and checks passed, but CO3b isn't ready to merge."

Now the builder's prompt asks it to end with one line of its own: `READY` (the round's work done, nothing asked) or
`QUESTION: <what needs deciding>`. The builder's prompt is main's (run_seat.py builds it), so a part branched long ago
is asked the same. A part goes to its verifier only with a green test record and READY:
- QUESTION: the part stops, with the question as the stop's words (the conductor answers it or takes it to the owner);
- neither (a question in prose, or no line at all): the part stays building, and run_seat.py and the board say the
  builder has not said it is ready, with its last words. Never "ready for the verifier".
"""
from __future__ import annotations

import json

import pytest

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_owner_line_waiting import board as board_of
from test_seat_failure import rec, run_seat, state, verifying

GR1B = ("**Questions for the owner** (each built as ruled; recommendation first)\n"
        "1. **\"Nothing was made\" can be wrong:** ... Should the message (a) say the outcome isn't known and to check "
        "your cases before retrying, or (b) stay as ruled? For now it also links to the case list.\n"
        "3. **\"Existing dataset\" with none selected:** it shows the ruled \"That dataset cannot be used for a new case\". "
        "Should it (a) say \"Select a dataset\" instead, or (b) stay as it is?")
CO3B = ("CO3b is still stopped: `test-file-coverage-check` is red, I've made no changes, and I still need an answer.\n\n"
        "**Question:** should I (a, recommended) remove the `Valkey` import and its type hints from the new test; (b) wait "
        "for the checker to be changed first, with a failing test; or (c, not advised) have the owner list the test as "
        "needing a live service?\n\nThe commits are `1dd8e1a` and `a11e7e2`. The frozen acceptance and checks passed, "
        "but CO3b isn't ready to merge.")


def ended(text, session="b-end"):
    return {"type": "result", "subtype": "success", "is_error": False, "num_turns": 40, "session_id": session,
            "result": text, "usage": {}, "total_cost_usd": 1.0}


def at_builder_green(w):
    """S1 green at its tip, its phase building, as when its builder's session ends."""
    wt, tip = verifying(w)
    st = state(w)
    st["phase"] = "building"
    (rec(w) / "state.json").write_text(json.dumps(st))
    return tip


def said(p):
    return p.stdout + p.stderr


@pytest.mark.parametrize("text", [GR1B, CO3B], ids=["GR1b-questions-for-the-owner", "CO3b-isnt-ready-to-merge"])
def test_a_builder_ending_on_a_question_in_prose_is_not_sent_to_the_verifier(world, text):
    w = world
    at_builder_green(w)
    p, _ = run_seat(w, "builder", [ended(text)])
    assert "ready for the verifier" not in said(p), said(p)
    assert state(w)["phase"] != "verifying", state(w)
    if state(w)["phase"] == "stopped":  # CO3b's ending has a line of its own beginning "Question:": its question stops it
        assert "should I (a, recommended)" in state(w)["note"], state(w)
    else:                              # GR1b's asks in prose: the part stays building, its builder's last words said
        assert state(w)["phase"] == "building" and "did not end with READY" in said(p) and "stay as it is?" in said(p), said(p)


def test_a_builder_ending_on_its_question_line_stops_the_part_with_the_question(world):
    w = world
    tip = at_builder_green(w)
    q = "should the empty list say 'No cases' (a) or stay silent (b)?"
    p, _ = run_seat(w, "builder", [ended(f"The page is built and its checks are green.\n\nQUESTION: {q}")])
    st = state(w)
    assert st["phase"] == "stopped" and q in st["note"] and tip[:10] in st["note"], st
    assert "ready for the verifier" not in said(p) and p.returncode != 0, said(p)


def test_a_builder_ending_ready_goes_to_the_verifier_as_before(world):
    w = world
    tip = at_builder_green(w)
    p, _ = run_seat(w, "builder", [ended("The round's work is done: the two cases are closed.\n\nREADY")])
    assert state(w)["phase"] == "verifying" and state(w)["tip"] == tip, state(w)
    assert f"green at {tip[:10]}; ready for the verifier." in said(p), said(p)


@pytest.mark.parametrize("text", [
    "QUESTION: which of the two captions?\n\nREADY",
    "READY\n\nOne more thing: should the caption say 'cases' or 'your cases'?",
    "Done, I think.",
], ids=["ready-under-a-question", "a-question-after-ready", "no-line"])
def test_ready_counts_only_as_the_last_line_with_no_question_line_above_it(world, text):
    w = world
    at_builder_green(w)
    p, _ = run_seat(w, "builder", [ended(text)])
    assert state(w)["phase"] != "verifying" and "ready for the verifier" not in said(p), (state(w), said(p))


def test_the_builders_prompt_asks_for_the_ending_line(world):
    w = world
    at_builder_green(w)
    prompts = w["tmp"] / "prompts.json"
    run_seat(w, "builder", [ended("READY")])
    prompt = json.loads(prompts.read_text())[0]
    assert "`READY`" in prompt and "`QUESTION: " in prompt, prompt[-600:]


def test_the_board_does_not_show_a_green_part_whose_builder_has_not_said_ready_as_waiting_for_its_verifier(world):
    w = world
    at_builder_green(w)
    run_seat(w, "builder", [ended(GR1B)])
    row, entry = board_of(w)
    assert row.split()[2] == "building" and "verifier pending" not in row, row
    assert "not said it is ready" in entry.get("note", "") and "stay as it is?" in entry.get("note", ""), entry
