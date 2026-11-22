"""No fifth round without the scout's table (LINE_FIXES_5_BRIEF.md, D; the owner, 21 November 2026): after a slice's
fourth round a read-only scout lists every open case as a table, and rounds 5 to 8 are judged against it. run_seat.py
refuses to start a builder round from 5 on until `slices/<ID>_ROUND<N>_TABLE.md` (N 5 or more, not empty) is in the main
checkout beside the slice's brief, and names the table in the builder's prompt when it is.
"""
from __future__ import annotations

import json

import pytest

from test_gates import world  # noqa: F401  (world is a fixture)
from test_seat_failure import builder_done, run_seat, verifying

V062 = "OspreyFlow_Build/process/lanes/v062"


def at_round(w, n):
    wt, tip = verifying(w, round_=n, limit=8)
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


@pytest.mark.parametrize("name,text", [("S1_ROUND4_TABLE.md", None), ("S1_ROUND5_TABLE.md", ""),
                                       ("S2_ROUND5_TABLE.md", None), ("S1_ROUND5_NOTES.md", None)],
                         ids=["round-4-table", "empty", "another-slice", "not-a-table"])
def test_only_a_round_5_or_later_table_of_that_slice_counts(world, name, text):
    w = world
    at_round(w, 6)
    table(w, name, *([text] if text is not None else []))
    p, calls = run_seat(w, "builder", [builder_done()])
    assert p.returncode != 0 and calls == [], p.stdout + p.stderr


@pytest.mark.parametrize("n,name", [(5, "S1_ROUND5_TABLE.md"), (6, "S1_ROUND6_TABLE.md"), (7, "S1_ROUND5_TABLE.md")])
def test_with_the_table_the_round_starts(world, n, name):
    w = world
    at_round(w, n)
    table(w, name)
    p, calls = run_seat(w, "builder", [builder_done()])
    assert calls == ["default"], p.stdout + p.stderr


def test_rounds_1_to_4_need_no_table(world):
    w = world
    at_round(w, 4)
    p, calls = run_seat(w, "builder", [builder_done()])
    assert calls == ["default"], p.stdout + p.stderr
