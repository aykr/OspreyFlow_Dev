"""The plan page's build ids, of every prefix length in use (LINE_FIXES_5_BRIEF.md, 1; PLAN_ID_PATTERN.diff).

`common.plan_ids()` read `[A-Z]{2}\\d+` only, so a build with a longer prefix (NET1 and DOC1, until the owner renamed
them NW1 and DC1 on 20 November 2026) was "not in the plan": never started, never written to the status file. The real
page (`Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/index.html`, on this Mac only) holds 58 ids on 21
November 2026, every prefix two letters; the pattern now takes two to four.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from test_gates import sh, started, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
PLAN = "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/index.html"
REAL = Path(__file__).resolve().parents[4] / PLAN


def plan(w, *ids):
    (w["repo"] / PLAN).write_text("const N=[\n" + "".join(f'["{i}",6,1,"None","x",[],""],\n' for i in ids) + "];")


def plan_ids(w):
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import common as c; "
            "print(json.dumps(sorted(c.plan_ids())))")
    return json.loads(sh([w["py"], "-c", code], w["repo"], w["env"]).stdout)


def test_a_plan_page_with_one_id_of_each_prefix_length_is_read_whole(world):
    w = world
    plan(w, "CO1", "NET1", "DOCS12", "BL1")
    assert plan_ids(w) == ["BL1", "CO1", "DOCS12", "NET1"]


def test_a_slice_of_a_three_letter_build_starts(world):
    w = world
    plan(w, "NET1", "CO1")
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("S1\tCO1\t", "S1\tNET1\t"))
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: S1 NET1' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    p, _ = started(w)
    assert p.returncode == 0 and "not in the plan" not in p.stdout + p.stderr, p.stdout + p.stderr


@pytest.mark.skipif(not REAL.is_file(), reason="the owner's plan page is on his Mac only (gitignored)")
def test_every_id_on_the_real_plan_page_is_read(world):
    w = world
    text = REAL.read_text()
    (w["repo"] / PLAN).write_text(text)
    every = sorted(set(re.findall(r'\[\s*"([A-Z]+\d+)"\s*,\s*\d+\s*,', text)))
    assert every and plan_ids(w) == every
