"""Step 4 dry run, end to end, offline (the orchestrator's suggestion, 14 November 2026): the live
gate (`tests/perf/test_search_budget_live.py`) run whole, as step 4 runs it, against the stub
Conduit of `tests/test_measure_search.py`, each case writing its result; then the record's table
made from them (`process/lanes/platform/v052-measure/results_table.py`). So Monday is only filling
it in, and a change that would leave a measure out of the record, or call one met that was not
measured, is red here first."""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

from tests import test_measure_search as tms

CONTROLS, LEAKS, _Conduit, _run_live = tms.CONTROLS, tms.LEAKS, tms._Conduit, tms._run_live
#: The stub Conduit, the measure tests' own fixture.
conduit = tms.conduit

_PATH = Path(__file__).resolve().parents[1] / "process/lanes/platform/v052-measure/results_table.py"
_SPEC = importlib.util.spec_from_file_location("results_table", _PATH)
assert _SPEC and _SPEC.loader
table = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(table)


def _dry_run(conduit: str, tmp_path: Path) -> tuple[dict[str, dict], str]:
    results = tmp_path / "results"
    first = _run_live(tmp_path, conduit, {"OSPREY_MEASURE_RESULTS": str(results)})
    assert first.returncode == 0, first.stdout[-1500:]
    _Conduit.leak_world = True
    leaks = tmp_path / "leaks.jsonl"
    leaks.write_text("\n".join(json.dumps(c) for c in LEAKS))
    second = _run_live(tmp_path, conduit, {
        "OSPREY_MEASURE_RESULTS": str(results), "OSPREY_MEASURE_PART_TOKEN": "part",
        "OSPREY_MEASURE_CONTROLS": json.dumps(CONTROLS), "OSPREY_MEASURE_LEAKS": str(leaks),
    }, only="m10")  # fmt: skip
    assert second.returncode == 0, second.stdout[-1500:]
    found = table.load(results)
    text = table.render(found, {"run": "dry run (stub Conduit)", "stack": "none", "lease": "none",
                                "commit": "the branch's head"})  # fmt: skip
    out = os.environ.get("STEP4_DRY_RUN_OUT")
    if out:
        Path(out).write_text(text, encoding="utf-8")
    return found, text


def test_the_live_gate_run_whole_gives_the_record_every_measure_s_row(
    conduit: str, tmp_path: Path
) -> None:
    found, text = _dry_run(conduit, tmp_path)
    assert sorted(found) == ["M1", "M10", "M3", "M4", "M5", "M6"], "what the stub can answer"
    rows = {
        line.split("|")[1].strip(): line
        for line in text.splitlines()
        if re.match(r"\| M\d+ ", line)
    }
    assert sorted(rows) == sorted(m for m, _w, _e in table.MEASURES), "a measure left out"
    for measure in found:
        assert "**met**" in rows[measure], rows[measure]
    for measure in ("M2", "M7", "M8", "M11"):
        assert "not measured here" in rows[measure] and "**met**" not in rows[measure]
    assert "**not measured**" in rows["M9"], "M9 skipped with no container named, never met"
    assert "p95 > 300 ms, or any over 2 s" in rows["M1"]


def test_a_measure_with_no_result_is_never_shown_met() -> None:
    text = table.render({}, {})
    rows = [line for line in text.splitlines() if re.match(r"\| M\d+ ", line)]
    assert len(rows) == len(table.MEASURES)
    assert not any("**met**" in r for r in rows)
    assert "(to be filled in)" in text


def test_every_row_s_figures_are_the_amendment_s() -> None:
    """The record's figures are the amendment's: a measure added to or dropped from the table, or a
    figure changed there, shows in the record, never a figure typed in the renderer."""
    figures = table.amendment_figures()
    assert sorted(figures) == sorted(m for m, _w, _e in table.MEASURES)
    assert figures["M1"] == ("≤ 300 ms", "p95 > 300 ms, or any over 2 s")
    assert figures["M10"][1] == "any"


def test_an_unmeasured_m10_is_shown_unmeasured_with_its_reached_count_never_met() -> None:
    """The orchestrator's ruling of 14 November 2026: under 90% of the controls reached, M10 is
    unmeasured, and the record says how many reached, never met and never a leak."""
    m10 = {"measure": "M10", "cases": 500, "reached": 428, "verdict": "unmeasured",
           "failures": [], "indeterminate": ["case 1: … proves nothing"] * 72}  # fmt: skip
    [row] = [r for r in table.render({"M10": m10}, {}).splitlines() if r.startswith("| M10 ")]
    assert "**unmeasured**" in row and "**met**" not in row, row
    assert "500 (428 reached)" in row and "only 428 of 500 controls reached" in row, row
