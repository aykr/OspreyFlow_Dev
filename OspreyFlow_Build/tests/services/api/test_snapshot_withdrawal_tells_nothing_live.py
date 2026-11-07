"""ADR-110 Amendment 15 (the owner's ruling "Only the rows' events"), rule 3: a full snapshot's
withdrawal tells its loader the same whatever another case holds, through the whole run path, on the
real stores.

Before the ruling, whether a dropped row's link went depended on other cases' rows and loads (the
ledger's `elements_kept_by_other_rows` and `elements_in_other_records`). So the run's counts, the
live links and the timeline differed with data the loader may not read. Now the withdrawal takes
back only the dropped rows' own events, by the ids their keys record, and never touches the graph.

This drives the real path: `run_recipe_as` (its ledger row, its metering) over the throwaway
Postgres's run ledger (`RecipeRunStore`), whose load is `run_published_recipe` with
`withdraw_dropped` over the real ArcadeDB adapter (`arcadedb_adapter`) and DuckDB analytics. Two
principals load two cases (`_loader` says why neither is confined to a dataset yet). In each of two
worlds, the loader
runs the published pipeline into their case three times: rows A and B; A alone (B dropped); A and B
(B back). In the second world, between the first two, the other case's loader runs **the same
pipeline** into their case with B's own row and a row linking B's node to one of their own.

It compares, between the worlds, everything the loader is told of the second and third runs, and
what each of those runs changed of what they read:
- the whole `ScheduleRunView` (as `GET …/runs` answers) and the whole `report_view`, the third
  run's `edges_created` with them;
- the live nodes and live links (type, ends and occurrences) around their case's nodes;
- their case's timeline events (type, time and ends).
The change, not the state: the other case's own row lands on the same pair and merges into the same
link before any withdrawal (a cross-case merge, outside this ruling; the studio REPORT has it), so
the states differ by that row whatever the withdrawal does.

It also says, in the first world, what the ruling says: the second run leaves every node and link,
and takes B's event alone. Only the ids and times that differ between any two runs are left out.

What a mistake would do, and what catches it (`L1.2a_RED_RECORD.md` has each shown red):
- a dropped row's link withdrawn (the graph changes in either world);
- a link withdrawn unless another row of any case holds it (`elements_kept_by_other_rows`): the
  live links, the timeline and the counts differ between the worlds;
- a link withdrawn unless another load's record lists it (`elements_in_other_records`): the same."""

from __future__ import annotations

import csv
import dataclasses
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import services.api.app as app_module
import services.api.recipe_run as run_module
from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from schemas.analytics import EventFilter, EventListRequest
from schemas.domain import ExpandRequest, Handling, Principal
from services.api.config import PostgresConfig
from services.api.load_records import report_view
from services.api.recipe_runs import RecipeRunStore
from services.api.studio_publish import run_published_recipe

from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_row_keys import ONTOLOGY, ROWS, SCHEME, _published_draft, _row

SOURCE = Handling(
    classification="OFFICIAL",
    handling_code="P",
    owning_unit="unit-1",
    originator="unit-1",
)
A, B = _row("SYN-1", "SYN-2", 1), _row("SYN-3", "SYN-4", 2)
#: The other case's rows: B's own pair again, and a link of their own on B's node.
THEIRS = [_row("SYN-3", "SYN-4", 2), _row("SYN-3", "SYN-8", 6)]
OWN_VALUES = ("SYN-1", "SYN-2", "SYN-3", "SYN-4")


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


def _loader(name: str) -> Principal:
    """A loader of one case. Not confined to a dataset (ADR-099): a Studio load stamps no dataset on
    what it writes until the load-into rule (L3.1, the studio lane's Part C), so a confined principal
    reads none of it, and the comparison would hold over nothing."""
    return Principal(id=name, clearance="SECRET", org_unit="unit-1")


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROWS[0]))
        writer.writeheader()
        writer.writerows(rows)


@dataclasses.dataclass
class World:
    runs: RecipeRunStore
    graph: Any
    analytics: Any
    repo: Path
    draft: Any
    monkeypatch: pytest.MonkeyPatch

    def _deps(self) -> app_module.RecipeRunDeps:
        names = [f.name for f in dataclasses.fields(app_module.RecipeRunDeps)]
        stand_ins: dict[str, Any] = {
            "recipe_runs": self.runs,
            "media": InMemoryMediaStore(),
        }
        return app_module.RecipeRunDeps(
            **{n: stand_ins.get(n, object()) for n in names}
        )  # type: ignore[arg-type]

    async def run(self, who: Principal, case: str, rows: list[dict[str, str]]) -> Any:
        """One full snapshot with *withdraw* of the published pipeline into `case`, as `who`."""
        _write(Path(self.draft.source_location), rows)

        async def execute(deps: Any, **kwargs: Any) -> Any:
            return await run_published_recipe(
                self.draft, kwargs["principal"], graph=self.graph, ontology=ONTOLOGY,
                load_id=new_id(), investigation_scope=kwargs["investigation_id"],
                repo_root=self.repo, analytics=self.analytics, media=kwargs["media"],
                scheme=SCHEME, sink=kwargs["sink"], withdraw_dropped=True,
            )  # fmt: skip

        self.monkeypatch.setattr(run_module, "_execute_recipe_run", execute)
        self.monkeypatch.setattr(
            run_module, "resolve_source_handling", lambda draft: SOURCE
        )
        report = await run_module.run_recipe_as(
            self._deps(), principal=who, recipe=self.draft, investigation_id=case,
            source_location=None, trigger="source_refresh",
        )  # fmt: skip
        row = (await self.runs.for_recipe(self.draft.recipe_id, limit=1))[0]
        run_view = app_module._schedule_run_view(row, who, SCHEME).model_dump(
            exclude={"run_id", "started_at", "finished_at", "load_id"}
        )
        said = report_view(report, who, SCHEME).model_dump(
            exclude={"load_id", "recipe_id"}
        )
        for view in (run_view, said):
            if view.get("metering"):
                view["metering"].pop("wall_ms", None)  # the clock, not the data
        return report, run_view, said

    async def what_they_read(self, who: Principal, case: str) -> dict[str, Any]:
        """The case's live nodes, live links and timeline, as `who` reads them, by value not id."""
        found = {}
        for value in (*OWN_VALUES, "SYN-8"):
            node = await self.graph.find_node(
                "Endpoint", "value_normalised", value, who
            )
            if node is not None:
                found[node.id] = value
        near = await self.graph.expand(
            ExpandRequest(node_ids=sorted(found), depth=1), who
        )
        values = {
            **found,
            **{n.id: str(n.properties.get("value_normalised")) for n in near.nodes},
        }
        links = sorted(
            (
                e.type,
                values.get(e.source, "?"),
                values.get(e.target, "?"),
                e.occurrences,
            )
            for e in near.edges
        )
        page = await self.analytics.list_events(
            EventListRequest(filter=EventFilter(investigation_scope=case), limit=100),
            who,
        )
        events = sorted(
            (e.edge_type, e.occurred_at.isoformat(), values.get(e.source_id, "?"),
             values.get(e.target_id, "?"))
            for e in page.events
        )  # fmt: skip
        return {"nodes": sorted(found.values()), "links": links, "events": events}


async def _told(
    runs: RecipeRunStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    beside: bool,
) -> dict[str, Any]:
    """One world: what the loader is told of the second and third runs, and what they read."""
    repo, draft = _published_draft(tmp_path / ("beside" if beside else "alone"))
    ours, theirs = new_id(), new_id()
    loader, other = _loader("loader-1"), _loader("loader-2")
    async with (
        arcadedb_adapter(ONTOLOGY, SCHEME) as graph,
        duckdb_adapter([], SCHEME) as analytics,
    ):
        world = World(runs, graph, analytics, repo, draft, monkeypatch)
        await world.run(loader, ours, [A, B])
        first = await world.what_they_read(loader, ours)
        if beside:
            await world.run(other, theirs, THEIRS)
        before_drop = await world.what_they_read(loader, ours)
        second, second_run, second_said = await world.run(loader, ours, [A])
        assert second.rows_withdrawn == 1, "B was dropped"
        after_drop = await world.what_they_read(loader, ours)
        _, third_run, third_said = await world.run(loader, ours, [A, B])
        after_back = await world.what_they_read(loader, ours)
    return {
        "first": first, "second_run": second_run, "second_said": second_said,
        "after_drop": after_drop, "third_run": third_run, "third_said": third_said,
        "after_back": after_back, "dropping": _change(before_drop, after_drop),
        "coming_back": _change(after_drop, after_back),
    }  # fmt: skip


def tuple_of(x: Any) -> Any:
    return tuple(x) if isinstance(x, list) else x


def _change(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """What a run changed of what the loader reads, by value: the nodes and events gone and come,
    and each link's change in occurrences (a link gone or come counts all of its). The other case's
    own writes are in both worlds' `before` or neither, so this is the run's own effect, which must
    not depend on them."""
    out: dict[str, Any] = {}
    for part in ("nodes", "events"):
        b, a = Counter(map(tuple_of, before[part])), Counter(map(tuple_of, after[part]))
        out[part] = (sorted((b - a).elements()), sorted((a - b).elements()))
    occurrences: Counter[tuple[str, str, str]] = Counter()
    for sign, state in ((-1, before), (1, after)):
        for kind, source, target, count in state["links"]:
            occurrences[(kind, source, target)] += sign * count
    out["links"] = sorted((k, n) for k, n in occurrences.items() if n)
    return out


async def test_a_snapshot_tells_its_loader_the_same_whatever_another_case_holds(
    runs: RecipeRunStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone = await _told(runs, tmp_path, monkeypatch, beside=False)
    beside = await _told(runs, tmp_path, monkeypatch, beside=True)
    # Between the worlds first: this is the rule-3 question, and its failure names the reason.
    for part in ("second_run", "second_said", "dropping", "third_run", "third_said",
                 "coming_back"):  # fmt: skip
        assert alone[part] == beside[part], part
    # Then what the ruling says, in the world with nobody else.
    first, dropped, back = alone["first"], alone["after_drop"], alone["after_back"]
    assert (dropped["nodes"], dropped["links"]) == (first["nodes"], first["links"]), (
        "Amendment 15: the graph is never touched"
    )
    assert len(first["events"]) == 2 and len(dropped["events"]) == 1, (
        "B's own event alone goes"
    )
    assert dropped["events"][0][2:] == ("SYN-1", "SYN-2")
    assert alone["third_said"]["edges_created"] == 0, "B's link never left: it merges"
    assert len(back["events"]) == 2
