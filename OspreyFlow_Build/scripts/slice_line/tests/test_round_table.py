"""No fifth round without the scout's table (LINE_FIXES_5_BRIEF.md, D; the owner, 21 November 2026): after a slice's
fourth round a read-only scout lists every open case as a table, and rounds 5 to 8 are judged against it. run_seat.py
refuses to start a builder round from 5 on until `slices/<ID>_ROUND<N>_TABLE.md`, N the round's own number (the
conductor, 25 November 2026), not empty, is in the main checkout beside the slice's brief, and names that table in the
builder's prompt.
"""
from __future__ import annotations

import json

import pytest

from test_gates import world  # noqa: F401  (world is a fixture)
from test_seat_failure import builder_done, run_seat, verifying

V062 = "OspreyFlow_Build/process/lanes/v062"


def at_round(w, n):
    wt, tip = verifying(w, round_=n, limit=max(8, n))
    f = w["data"] / "records/S1/state.json"
    f.write_text(json.dumps({**json.loads(f.read_text()), "phase": "building", "round": n}))
    return wt


def table(w, name, text="| case | open |\n| --- | --- |\n| 1 | yes |\n"):
    f = w["repo"] / V062 / "slices" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


def test_round_5_without_the_table_does_not_start(world):
    w = world
    at_round(w, 5)
    p, calls = run_seat(w, "builder", [builder_done()])
    assert p.returncode != 0 and calls == [], p.stdout + p.stderr
    assert "no round from 5 on starts without the scout's table" in p.stderr and "S1_ROUND5_TABLE.md" in p.stderr


@pytest.mark.parametrize("name,text", [("S1_ROUND4_TABLE.md", None), ("S1_ROUND6_TABLE.md", ""),
                                       ("S2_ROUND6_TABLE.md", None), ("S1_ROUND6_NOTES.md", None)],
                         ids=["round-4-table", "empty", "another-slice", "not-a-table"])
def test_only_a_round_5_or_later_table_of_that_slice_counts(world, name, text):
    w = world
    at_round(w, 6)
    table(w, name, *([text] if text is not None else []))
    p, calls = run_seat(w, "builder", [builder_done()])
    assert p.returncode != 0 and calls == [], p.stdout + p.stderr


@pytest.mark.parametrize("n,name", [(5, "S1_ROUND5_TABLE.md"), (6, "S1_ROUND6_TABLE.md"), (10, "S1_ROUND10_TABLE.md")])
def test_with_the_table_the_round_starts(world, n, name):
    w = world
    at_round(w, n)
    table(w, name)
    p, calls = run_seat(w, "builder", [builder_done()])
    assert calls == ["default"], p.stdout + p.stderr


def prompt(w):
    return json.loads((w["tmp"] / "prompts.json").read_text())[0]


@pytest.mark.parametrize("n", [6, 10])
def test_the_builder_gets_the_table_whose_number_is_its_rounds_own(world, n):
    """The conductor, 25 November 2026: the first table in name order was taken, so ROUND10 beat ROUND6, 11 and 12,
    and builders got their part's oldest table. ROUND6 and ROUND10 side by side, as the slices folder holds them."""
    w = world
    at_round(w, n)
    table(w, "S1_ROUND6_TABLE.md", "| case | open |\n| --- | --- |\n| six | yes |\n")
    table(w, "S1_ROUND10_TABLE.md", "| case | open |\n| --- | --- |\n| ten | yes |\n")
    p, calls = run_seat(w, "builder", [builder_done()])
    assert calls == ["default"], p.stdout + p.stderr
    said = prompt(w)
    assert f"S1_ROUND{n}_TABLE.md" in said, said
    other = 10 if n == 6 else 6
    assert f"S1_ROUND{other}_TABLE.md" not in said, said


@pytest.mark.parametrize("n,held", [(7, ["S1_ROUND5_TABLE.md"]), (11, ["S1_ROUND6_TABLE.md", "S1_ROUND10_TABLE.md"]),
                                    (12, ["S1_ROUND6_TABLE.md", "S1_ROUND10_TABLE.md", "S1_ROUND13_TABLE.md"])])
def test_a_round_whose_own_table_is_missing_does_not_start_whatever_other_tables_there_are(world, n, held):
    w = world
    at_round(w, n)
    for name in held:
        table(w, name)
    p, calls = run_seat(w, "builder", [builder_done()])
    assert p.returncode != 0 and calls == [], p.stdout + p.stderr
    assert f"S1_ROUND{n}_TABLE.md" in p.stderr, p.stderr


@pytest.mark.parametrize("held", [False, True], ids=["none", "a-round-4-table"])
def test_rounds_1_to_4_need_no_table(world, held):
    w = world
    at_round(w, 4)
    if held:
        table(w, "S1_ROUND4_TABLE.md")
    p, calls = run_seat(w, "builder", [builder_done()])
    assert calls == ["default"], p.stdout + p.stderr
    assert "_TABLE.md" not in prompt(w)                                      # rounds 1 to 4 are not judged on a table
