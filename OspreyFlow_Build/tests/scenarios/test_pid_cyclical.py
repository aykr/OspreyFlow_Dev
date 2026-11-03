"""Chapter 3's cyclical grid, proved over the generated data (ADR-120 Amendment 18; build order
step 16).

The timeline's Cyclical view counts every dated event of the case by weekday and hour (UTC): one
event per edge a load writes with a `temporal.at`. Chapter 3 says the grid peaks between 08:00 and
12:00 and 13:00 and 16:00, when the yards are in use, and that weekends carry about a third. In the
2 November rehearsal one cell (Thursday 11:00) held 38,761 events: a PIN call link's single-call
week was placed at its week's midpoint (Monday 00:00:00 plus half a week, Thursday 11:59:59), and
every even spread began at 00:00:00 and ended at 23:59:59, so the calls, which outnumber every
other event about four to one, drew the artefacts of the placement rule rather than a day.

What is read is what the analytics store receives: for every file the seed loads before the analyst
begins (`pid_files.seed_stages("seed")`), the column each of its recipe's edges binds as
`temporal.at`, on every row the plan writes (`pid_files.ordered_rows`, no I/O). Nothing here opens a
store or a socket.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from demo_fixtures import pid_files, pid_plan

RECIPES = Path(pid_files.__file__).parent

#: The script's hours (chapter 3: "08:00 to 12:00 and 13:00 to 16:00").
PEAK_HOURS = frozenset({8, 9, 10, 11, 13, 14, 15})
SATURDAY, SUNDAY = 5, 6
#: A uniform grid puts 1/168 (0.6%) in each cell; the establishment's day at its busiest (a Sunday
#: morning hour) about 1.8%. Rehearsal's spike was about 30%.
MAX_CELL_SHARE = 0.025


def _at_columns(recipe: str) -> list[str]:
    """The columns a recipe's edges bind as `temporal.at`."""
    spec = yaml.safe_load((RECIPES / recipe).read_text())
    columns: list[str] = []
    for edge in spec.get("row_template", {}).get("edges", []):
        at = (edge.get("temporal") or {}).get("at")
        if isinstance(at, dict) and "field" in at and at["field"] not in columns:
            columns.append(at["field"])
    return columns


@pytest.fixture(scope="module")
def grids() -> dict[str, Counter[tuple[int, int]]]:
    """Per file, and for all files together (`"*"`), the dated events by (weekday, hour)."""
    plan = pid_plan.build_plan("demo")
    out: dict[str, Counter[tuple[int, int]]] = {"*": Counter()}
    for stage in pid_files.seed_stages("seed"):
        columns = _at_columns(stage.recipe)
        if not columns:
            continue
        grid = out.setdefault(stage.file, Counter())
        for row in pid_files.ordered_rows(plan, stage.file):
            for column in columns:
                cell = row.values.get(column, "")
                if not cell:
                    continue
                when = datetime.fromisoformat(cell)
                grid[(when.weekday(), when.hour)] += 1
        out["*"].update(grid)
    return out


def _share(grid: Counter[tuple[int, int]], keep: Any) -> float:
    return sum(n for cell, n in grid.items() if keep(cell)) / sum(grid.values())


def test_the_grid_reads_the_calls_and_the_throw_overs(grids: dict[str, Counter[Any]]) -> None:
    """The reader sees what the load writes: every call and every throw-over is dated."""
    assert sum(grids[pid_files.CALLS].values()) == pid_plan.CALL_ROWS
    assert sum(grids["pid_throwover_log.csv"].values()) == pid_plan.TOTAL_THROW_OVERS


@pytest.mark.parametrize("which", ["*", pid_files.CALLS])
def test_no_weekday_hour_cell_holds_a_spike(grids: dict[str, Counter[Any]], which: str) -> None:
    """No cell holds more than 2.5% of the events: the rehearsal's Thursday 11:00 held about 30%."""
    grid = grids[which]
    cell, count = grid.most_common(1)[0]
    share = count / sum(grid.values())
    assert share <= MAX_CELL_SHARE, f"{which}: {cell} holds {count:,} ({share:.1%})"


def test_the_grid_peaks_in_the_hours_the_script_names(grids: dict[str, Counter[Any]]) -> None:
    """Most events fall in the script's hours, the ten busiest cells all do, and neither midnight
    column (where an even spread from 00:00:00 to 23:59:59 put its ends) stands out."""
    grid = grids["*"]
    assert _share(grid, lambda c: c[1] in PEAK_HOURS) >= 0.60
    busiest = [cell for cell, _n in grid.most_common(10)]
    assert all(hour in PEAK_HOURS for _day, hour in busiest), busiest
    for hour in (0, 23):
        assert _share(grid, lambda c, h=hour: c[1] == h) <= 0.03, hour


def test_weekends_carry_about_a_third_and_sunday_most(grids: dict[str, Counter[Any]]) -> None:
    grid = grids["*"]
    assert 0.30 <= _share(grid, lambda c: c[0] in (SATURDAY, SUNDAY)) <= 0.38
    by_day = Counter({d: sum(n for (day, _h), n in grid.items() if day == d) for d in range(7)})
    assert by_day.most_common(1)[0][0] == SUNDAY, by_day


def test_the_throw_overs_keep_the_script_figures(grids: dict[str, Counter[Any]]) -> None:
    """The throw-overs' own figures (chapter 3's 66%, 34% and 19%) are unchanged."""
    grid = grids["pid_throwover_log.csv"]
    total = pid_plan.TOTAL_THROW_OVERS
    assert sum(n for (_d, h), n in grid.items() if h in PEAK_HOURS) == 173  # 66%
    assert sum(n for (d, _h), n in grid.items() if d in (SATURDAY, SUNDAY)) == 90  # 34%
    assert sum(n for (d, _h), n in grid.items() if d == SUNDAY) == 50  # 19%
    assert round(173 / total * 100) == 66 and round(90 / total * 100) == 34
    assert round(50 / total * 100) == 19
