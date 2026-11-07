"""ADR-110 Amendment 15, rule 3: a full snapshot's withdrawal says the same to its loader whatever
another case holds, through the whole run path.

The review of L1.2a's Part A (7 November 2026) found the planner's choice of what to withdraw
reaching the loader's figures. A node withdrawn or kept moved "graph writes" in the run's metering,
on `GET …/recipes/{id}/runs`, and so did whether a link went or stayed. Both choices depended on
links and rows of another case. The owner ruled "Never withdraw nodes"; metering no longer counts a
withdrawal; and a kept link is counted only from this pipeline's own rows in the case.

So this drives the real path: `run_recipe_as`, with its metering, over the throwaway Postgres's run
ledger (`RecipeRunStore`); the load is the real `load_with_rules` with `withdraw_dropped`, over
`MergingGraph`. It runs the same two snapshots of one pipeline in one case twice. In the second
world, between them, another case's pipeline keeps a row that writes the dropped row's own link,
and another of its own on the dropped row's node, which the loader may not read. It then compares
everything the loader is told of the second snapshot, and what they can see in the graph:
- the whole `ScheduleRunView` (`app._schedule_run_view`, as `GET …/runs` answers);
- the whole `report_view`;
- which of the case's own nodes are still live.

Only the ids and times that differ between any two runs are left out. What a mistake would do, and
the case that catches it (`test_a_snapshot_says_the_same_whatever_another_case_holds`):

- a node withdrawn when nothing rests on it and kept when another case's link does (red with node
  withdrawal restored: the live nodes differ);
- metering counting the links the withdrawal took, which another case's row keeps (red with that
  count restored: `graph_writes` differs);
- a kept link counted because another case's row holds it (red with the count from every row
  restored: `links_kept_an_occurrence` and the notes differ)."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
import services.api.app as app_module
import services.api.recipe_run as run_module
from services.api.config import PostgresConfig
from services.api.load_records import report_view
from services.api.recipe_runs import RecipeRunStore
from services.api.studio_publish import load_with_rules

from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from schemas.domain import Handling
from tests.ingest.recipe_test_support import (
    MergingGraph,
    local_staging,  # noqa: F401 (the autouse fixture)
)
from tests.ingest.test_row_keys import LOADER, ONTOLOGY, SCHEME, _recipe, _row

SOURCE = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
A, B = _row("SYN-1", "SYN-2", 1), _row("SYN-3", "SYN-4", 2)
#: Another case's rows: B's own pair again (one link, its occurrence kept by that case's row), and
#: a link of its own on B's node, which the loader may not read.
THEIRS = [_row("SYN-3", "SYN-4", 2), _row("SYN-3", "SYN-8", 6)]
OWN_VALUES = {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}


class OtherCasesLinksHidden(MergingGraph):
    """The loader may not read a link only another case wrote (rule 3)."""

    def __init__(self) -> None:
        super().__init__(ONTOLOGY)
        self.hidden: set[str] = set()

    async def get_edges(self, edge_ids: Sequence[str], principal: Any) -> list[Any]:
        return [e for e in await super().get_edges(edge_ids, principal) if e.id not in self.hidden]


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


def _deps(runs: RecipeRunStore) -> app_module.RecipeRunDeps:
    names = [f.name for f in dataclasses.fields(app_module.RecipeRunDeps)]
    stand_ins: dict[str, Any] = {"recipe_runs": runs, "media": InMemoryMediaStore()}
    return app_module.RecipeRunDeps(**{n: stand_ins.get(n, object()) for n in names})  # type: ignore[arg-type]


async def _run(
    runs: RecipeRunStore,
    graph: OtherCasesLinksHidden,
    monkeypatch: pytest.MonkeyPatch,
    *,
    recipe_id: str,
    case: str,
    rows: list[dict[str, str]],
    withdraw: bool,
    hide: bool = False,
) -> Any:
    recipe = _recipe().model_copy(update={"id": recipe_id})

    async def execute(deps: Any, **kwargs: Any) -> Any:
        report, _, _ = await load_with_rules(
            recipe, rows, LOADER, graph=graph, ontology=ONTOLOGY, load_id=new_id(),  # type: ignore[arg-type]
            investigation_scope=case, source="private_cash.csv", media=kwargs["media"],
            rules=None, scheme=SCHEME, sink=kwargs["sink"], withdraw_dropped=withdraw,
        )  # fmt: skip
        if hide:
            graph.hidden |= set(report.created_edge_ids)
        return report

    monkeypatch.setattr(run_module, "_execute_recipe_run", execute)
    monkeypatch.setattr(run_module, "resolve_source_handling", lambda draft: SOURCE)
    draft = type("Draft", (), {"recipe_id": recipe_id, "version": 1})()
    return await run_module.run_recipe_as(
        _deps(runs), principal=LOADER, recipe=draft, investigation_id=case,  # type: ignore[arg-type]
        source_location=None, trigger="source_refresh",
    )  # fmt: skip


async def _told(
    runs: RecipeRunStore, monkeypatch: pytest.MonkeyPatch, *, another_case_holds: bool
) -> tuple[dict[str, Any], dict[str, Any], set[str]]:
    graph = OtherCasesLinksHidden()
    recipe_id, case = new_id(), new_id()
    await _run(runs, graph, monkeypatch, recipe_id=recipe_id, case=case, rows=[A, B], withdraw=True)
    if another_case_holds:
        await _run(runs, graph, monkeypatch, recipe_id=new_id(), case=new_id(), rows=THEIRS,
                   withdraw=False, hide=True)  # fmt: skip
    report = await _run(runs, graph, monkeypatch, recipe_id=recipe_id, case=case, rows=[A],
                        withdraw=True)  # fmt: skip
    assert report.rows_withdrawn == 1, "B was dropped"
    row = (await runs.for_recipe(recipe_id, limit=1))[0]
    run_view = app_module._schedule_run_view(row, LOADER, SCHEME).model_dump(
        exclude={"run_id", "started_at", "finished_at", "load_id"}
    )
    if run_view.get("metering"):
        run_view["metering"].pop("wall_ms", None)
    said = report_view(report, LOADER, SCHEME).model_dump(exclude={"load_id", "recipe_id"})
    if said.get("metering"):
        said["metering"].pop("wall_ms", None)  # the clock, not the data
    live = {str(n.properties["value_normalised"]) for n in graph.live_nodes.values()} & OWN_VALUES
    return run_view, said, live


async def test_a_snapshot_says_the_same_whatever_another_case_holds(
    runs: RecipeRunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone = await _told(runs, monkeypatch, another_case_holds=False)
    beside = await _told(runs, monkeypatch, another_case_holds=True)
    assert alone[0] == beside[0], "the run's row, as GET …/runs answers it"
    assert alone[1] == beside[1], "the load's report view"
    assert alone[2] == beside[2] == OWN_VALUES, "Amendment 15: no node of the case's goes"
