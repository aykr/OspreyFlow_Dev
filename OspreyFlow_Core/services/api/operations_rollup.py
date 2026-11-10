"""Admin › Running › Operations' figures from the run ledger (`06_DECISIONS.md` ADR-141 decisions
3, 4, 7 and 14; ADR-145 decision 9; the redesign's phase 10 step 1).

Pure: the route reads the window's runs (the reader's unit's alone, unless the reader administers
the system: phase 10 step 7) and the names, and this rolls them up.

**Rule 3 on every figure** (decision 7, ADR-110 decision 8): a day's row shows its runs' outcomes
and times to every reader, but a count of what its runs read, staged or wrote only where the reader
may view every marking those runs wrote at; otherwise the counts are `None` and `withheld`.
**Rule 7:** no account id is served. A run's owner is named (`ran_as_name`), and a refusal's words,
which the ledger writes with the owner's id in them, have that id replaced by the name.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from zoneinfo import ZoneInfo

from ontology.handling import HandlingScheme, principal_may_view
from schemas.domain import Principal
from schemas.operations import (
    ExternalTrigger,
    PausedPipeline,
    RefusalCount,
    RollupRow,
    SchedulerHealth,
)

from .recipe_runs import RecipeRun

_LONDON = ZoneInfo("Europe/London")
NO_NAME = "An account with no name on record"
NOT_RECORDED = "not recorded"


def _day(run: RecipeRun) -> date:
    return run.started_at.astimezone(_LONDON).date()


def _named(words: str | None, run: RecipeRun, names: Mapping[str, str]) -> str:
    text = words or "no reason was recorded"
    if run.run_as:
        text = text.replace(run.run_as, names.get(run.run_as, "the owner"))
    return text


def _sum(values: Iterable[int | None]) -> int | None:
    found = [v for v in values if v is not None]
    return sum(found) if found else None


def rollup_rows(
    runs: Sequence[RecipeRun],
    *,
    reader: Principal,
    scheme: HandlingScheme,
    labels: Mapping[str, str],
) -> list[RollupRow]:
    groups: dict[tuple[date, str, str], list[RecipeRun]] = defaultdict(list)
    for run in runs:
        groups[(_day(run), run.recipe_id, run.trigger)].append(run)
    rows: list[RollupRow] = []
    for (day, recipe_id, trigger), group in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]), reverse=True
    ):
        may = all(principal_may_view(m, reader, scheme) for r in group for m in r.markings)
        metered = [r.metering for r in group if r.metering is not None]
        rows.append(
            RollupRow(
                day=day,
                pipeline_id=recipe_id,
                pipeline_label=labels.get(recipe_id, "a pipeline no longer listed"),
                dataset_id=group[0].dataset_id,
                unit=group[0].owning_unit or NOT_RECORDED,
                trigger=trigger,  # type: ignore[arg-type]
                runs=len(group),
                succeeded=sum(r.outcome == "succeeded" for r in group),
                refused=sum(r.outcome == "refused" for r in group),
                failed=sum(r.outcome == "failed" for r in group),
                wall_ms=sum(m.wall_ms for m in metered),
                rows_read=_sum(r.rows_read for r in group) if may else None,
                rows_staged=_sum(m.rows_staged for m in metered) if may else None,
                graph_writes=_sum(m.graph_writes for m in metered) if may else None,
                withheld=not may,
            )
        )
    return rows


def scheduler_health(
    runs: Sequence[RecipeRun],
    *,
    paused: Sequence[PausedPipeline],
    names: Mapping[str, str],
) -> SchedulerHealth:
    refused: dict[str, int] = defaultdict(int)
    for run in runs:
        if run.outcome == "refused":
            refused[_named(run.failure, run, names)] += 1
    return SchedulerHealth(
        skipped=sum(r.outcome == "skipped" for r in runs),
        missed=sum(r.outcome == "missed" for r in runs),
        refused=[
            RefusalCount(reason=k, count=v)
            for k, v in sorted(refused.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        paused=list(paused),
        running_now=sum(r.outcome == "running" for r in runs),
    )


def external_triggers(
    runs: Sequence[RecipeRun],
    *,
    reader: Principal,
    scheme: HandlingScheme,
    labels: Mapping[str, str],
    names: Mapping[str, str],
) -> list[ExternalTrigger]:
    found: list[ExternalTrigger] = []
    for run in runs:
        if run.trigger != "external":
            continue
        may = all(principal_may_view(m, reader, scheme) for m in run.markings)
        found.append(
            ExternalTrigger(
                run_id=run.run_id,
                pipeline_label=labels.get(run.recipe_id, "a pipeline no longer listed"),
                service_identity=run.triggered_by or NOT_RECORDED,
                ran_as_name=names.get(run.run_as, NO_NAME),
                started_at=run.started_at,
                outcome=run.outcome,
                wall_ms=run.metering.wall_ms if run.metering is not None else None,
                withheld=not may,
            )
        )
    return found
