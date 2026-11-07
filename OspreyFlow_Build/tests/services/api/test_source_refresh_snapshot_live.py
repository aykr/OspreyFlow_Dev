"""ADR-110 Amendments 6, 8 and 15: a second full snapshot missing one row withdraws exactly that
row's links and events, never its nodes, and the refresh's revert restores them.

Live, end to end, through the path a source refresh takes (`run_published_recipe` with
`withdraw_dropped`, a `LedgerSink` over the real run ledger): ArcadeDB on `ARCADEDB_HTTP_PORT`,
Postgres on `POSTGRES_PORT`, DuckDB in memory. Synthetic rows only (rule 9). What a mistake would
do, and the case that catches it:

- the dropped row left in the graph or its events in the timeline, or a kept row taken with it
  (`test_a_second_snapshot_missing_one_row_withdraws_it_and_the_revert_restores_it`);
- a row that comes back in a third snapshot skipped as kept, or matched to its withdrawn node, or
  its events counted twice (`test_a_row_that_comes_back_is_loaded_again_once`);
- the refresh's revert restoring a row that came back (the same file's second case)."""

from __future__ import annotations

import csv
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from services.api.config import PostgresConfig
from services.api.load_records import LedgerSink
from services.api.recipe_runs import RecipeRunStore
from services.api.studio_publish import run_published_recipe
from services.ingest.load_revert import RevertDeps, RevertRefused, revert
from services.ingest.watermark import RefreshRead

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from schemas.analytics import EventFilter, EventListRequest
from schemas.domain import Handling
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_revert_load import Alerts, Audit, Held, Steps, WorkingSets, no_caches
from tests.ingest.test_row_keys import LOADER, ONTOLOGY, ROWS, SCHEME, _published_draft

NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)
SOURCE = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
A, B, C = ROWS


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROWS[0]))
        writer.writeheader()
        writer.writerows(rows)


class Refresh:
    """One case's refreshes of one file: each a ledger run and a load, as the executor runs."""

    def __init__(self, tmp_path: Path, runs: RecipeRunStore, graph: object, analytics: object):
        self.repo, draft = _published_draft(tmp_path)
        self.case = new_id()
        self.draft = draft.model_copy(update={"recipe_id": draft.recipe_id})
        self.file = Path(draft.source_location or "")
        self.runs, self.graph, self.analytics = runs, graph, analytics
        #: Each refresh starts after the one before, as the executor's lock makes them.
        self.started = NOW

    async def snapshot(
        self, rows: list[dict[str, str]], read: RefreshRead | None = None
    ) -> object:
        """One refresh of the file: a full snapshot with *withdraw*, or as `read` says."""
        _write(self.file, rows)
        self.started += timedelta(minutes=1)
        run_id = await self.runs.start(
            recipe_id=self.draft.recipe_id, recipe_version=1, investigation_id=self.case,
            trigger="source_refresh", slot=None, run_as=LOADER.id, source=SOURCE,
            now=self.started,
        )  # fmt: skip
        sink = LedgerSink(
            self.runs, run_id, created_by=LOADER.id, investigation_id=self.case, started_at=NOW
        )
        load_id = new_id()
        report = await run_published_recipe(
            self.draft,
            LOADER,
            graph=self.graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id=load_id,
            investigation_scope=self.case,
            repo_root=self.repo,
            analytics=self.analytics,  # type: ignore[arg-type]
            media=InMemoryMediaStore(),
            scheme=SCHEME,
            sink=sink,
            withdraw_dropped=read is None,
            refresh=read,
        )
        await self.runs.finish(run_id, report=report, now=self.started)
        return report

    async def values(self) -> set[str]:
        found = set()
        for value in ("SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5", "SYN-6"):
            node = await self.graph.find_node(  # type: ignore[attr-defined]
                "Endpoint", "value_normalised", value, LOADER
            )
            if node is not None:
                found.add(value)
        return found

    async def events(self) -> int:
        page = await self.analytics.list_events(  # type: ignore[attr-defined]
            EventListRequest(filter=EventFilter(investigation_scope=self.case), limit=100), LOADER
        )
        return int(page.total)

    async def revert(self, load_id: str) -> None:
        steps = Steps()
        deps = RevertDeps(
            ledger=self.runs,  # type: ignore[arg-type]
            graph=self.graph,  # type: ignore[arg-type]
            analytics=self.analytics,  # type: ignore[arg-type]
            held_rows=Held(steps),
            alerts=Alerts(steps),
            audit=Audit(steps),
            working_sets=WorkingSets(steps),
            invalidate_caches=no_caches,
        )
        await revert(load_id, reverted_by="operator-1", deps=deps, now=NOW)


async def test_a_second_snapshot_missing_one_row_withdraws_it_and_the_revert_restores_it(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph, duckdb_adapter([], SCHEME) as analytics:
        refresh = Refresh(tmp_path, runs, graph, analytics)
        first = await refresh.snapshot([A, B, C])
        assert first.rows_withdrawn == 0  # type: ignore[attr-defined]
        assert await refresh.values() == {"SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5", "SYN-6"}
        assert await refresh.events() == 3

        second = await refresh.snapshot([A, C])

        assert second.rows_already_loaded == 2 and second.rows_withdrawn == 1  # type: ignore[attr-defined]
        # ADR-110 Amendment 15: the dropped row's link and its event go; its nodes never do.
        assert second.withdrawn_node_ids == [] and len(second.withdrawn_edge_ids) == 1  # type: ignore[attr-defined]
        assert await refresh.values() == {"SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5", "SYN-6"}
        assert await refresh.events() == 2, "the dropped row's event leaves the timeline too"
        assert await graph.get_edges(second.withdrawn_edge_ids, LOADER) == []  # type: ignore[attr-defined]

        await refresh.revert(second.load_id)  # type: ignore[attr-defined]

        assert await refresh.values() == {"SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5", "SYN-6"}
        assert await refresh.events() == 3
        # Its key is kept again: the same snapshot run now withdraws it once more, not twice.
        again = await refresh.snapshot([A, C])
        assert again.rows_withdrawn == 1  # type: ignore[attr-defined]


async def test_a_row_that_comes_back_is_loaded_again_once(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph, duckdb_adapter([], SCHEME) as analytics:
        refresh = Refresh(tmp_path, runs, graph, analytics)
        await refresh.snapshot([A, B, C])
        second = await refresh.snapshot([A, C])

        back = await refresh.snapshot([A, B, C])

        # Its nodes never left (Amendment 15): matched, not created; its link is written again.
        assert back.rows_already_loaded == 2 and back.nodes_created == 0  # type: ignore[attr-defined]
        assert back.created_edge_ids and not set(back.created_edge_ids) & set(second.withdrawn_edge_ids)  # type: ignore[attr-defined]
        assert await refresh.values() == {"SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5", "SYN-6"}
        assert await refresh.events() == 3, "each event held once"
        # The refresh that withdrew B is not reverted while B is loaded again.
        with pytest.raises(RevertRefused) as refused:
            await refresh.revert(second.load_id)  # type: ignore[attr-defined]
        assert [r.reason for r in refused.value.refusals] == ["withdrawn_rows_loaded_again"]
        assert await refresh.events() == 3
