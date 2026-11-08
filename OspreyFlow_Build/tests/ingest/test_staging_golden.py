"""Golden files for each staging step (the redesign's phase 7; ADR-140 decision 11; rule 8: every
step of guided mode's closed catalogue is a Knowledge Adapter with golden test files).

Each `golden/staging/<case>.json` holds a step list, the source tables and reference lists it runs
over (synthetic, rule 9), and what must come out: the table's columns, every row's cells and refs
(which source row each came from), each step's report, and every rejection with its cause. A
change to what a step does changes its golden file, in review, or this test fails.

What a mistake would do, and the case that catches it:

- a step kind with no golden file (`test_every_step_kind_has_a_golden_file`);
- a row lost without a word: each case's `reports` and `rejections` account for every input row
  (`test_every_input_row_is_accounted_for`);
- a staged row's refs not naming the rows it came from (each case's `expected.rows[].refs`; the
  Join's provenance has its own test, `test_staged_run.py`)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter
from services.ingest.staging_catalogue import (
    StagingResult,
    reference_table,
    run_staging,
    source_table,
)

from schemas.dataset_model import ReferenceList
from schemas.staging import StagingStep

GOLDEN = Path(__file__).parent / "golden" / "staging"
STEPS = TypeAdapter(list[StagingStep])
KINDS = {"lookup", "join", "filter", "derive", "union", "dedupe"}


def run_case(case: dict[str, Any]) -> StagingResult:
    sources = {
        name: source_table(name, s["rows"], load_id=s["load_id"], key=s.get("key"))
        for name, s in case["sources"].items()
    }
    lists = {
        name: reference_table(ReferenceList.model_validate(rl["meta"]), rl["rows"])
        for name, rl in case["lists"].items()
    }
    return run_staging(
        STEPS.validate_python(case["steps"]),
        sources=sources,
        lists=lists,
        dataset_id=case["dataset_id"],
        subscribed=case.get("subscribed", []),
    )


def outcome(result: StagingResult) -> dict[str, Any]:
    """What a golden file records of a run: refs as `[source, row_index, row_key, load_id]`."""

    def refs(rs: Any) -> list[list[Any]]:
        return [[r.source, r.row_index, r.row_key, r.load_id] for r in rs]

    return {
        "columns": result.output.columns,
        "rows": [{"cells": row.cells, "refs": refs(row.refs)} for row in result.output.rows],
        "reports": [asdict(r) for r in result.reports],
        "rejections": [
            {"step": r.step, "side": r.side, "refs": refs(r.refs), "reason": r.reason}
            for r in result.rejections
        ],
    }


def _cases() -> list[str]:
    return sorted(p.stem for p in GOLDEN.glob("*.json"))


def _load(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", _cases())
def test_each_step_gives_its_golden_table(name: str) -> None:
    case = _load(name)
    assert "expected" in case, f"{name} has no expected outcome"
    assert outcome(run_case(case)) == case["expected"]


def test_every_step_kind_has_a_golden_file() -> None:
    covered = {step["kind"] for name in _cases() for step in _load(name)["steps"]}
    assert covered == KINDS, KINDS - covered


@pytest.mark.parametrize("name", _cases())
def test_every_input_row_is_accounted_for(name: str) -> None:
    """Rule 2 per step, from what the step itself gave (`run_case`), not from the golden file: every
    row in is passed on, counted (unmatched, filtered out, a repeat folded) or rejected. For a
    Join each side is checked: a row of either table that met nothing is counted."""
    case = _load(name)
    result = run_case(case)
    steps = {s.id: s for s in STEPS.validate_python(case["steps"])}
    for report in result.reports:
        step = steps[report.step]
        if report.kind != "join":
            lost = report.filtered_out + report.repeats_folded + report.rejected
            assert report.rows_out == report.rows_in - lost, report
            continue
        out = result.tables[report.step].rows
        mine = [r for r in result.rejections if r.step == report.step]
        for side, table, rows_in, unmatched in (
            ("left", step.left, report.rows_in, report.unmatched),
            ("right", step.right, report.right_rows_in, report.right_unmatched),
        ):
            first = {(ref.source, ref.row_index) for ref in result.tables[table].rows[0].refs}
            source = next(iter(first))[0]
            met = {
                (ref.source, ref.row_index)
                for row in out
                for ref in row.refs
                if ref.source == source
            }
            if side == "left" and step.how == "left":
                met_count = len(met) - unmatched  # a kept unmatched left row is in the output
            else:
                met_count = len(met)
            rejected = sum(1 for r in mine if r.side == side)
            assert rows_in == met_count + unmatched + rejected, (name, side, report)
