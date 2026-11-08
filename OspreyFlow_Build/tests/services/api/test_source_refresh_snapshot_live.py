"""ADR-110 Amendments 6, 8 and 15: a second full snapshot missing one row withdraws only that row's
own events, never a node or a link, and the refresh's revert restores them.

Live, through the load a source refresh makes (`run_published_recipe` with `withdraw_dropped`, a
`LedgerSink` over the real run ledger), on the raw adapter with an unconfined loader: what the
withdrawal does, not who may see it. Its dataset stamping and confinement are
`test_studio_load_stamps_its_case_dataset_live.py`'s, and the comparison across cases is
`test_snapshot_withdrawal_tells_nothing_live.py`'s. ArcadeDB on `ARCADEDB_HTTP_PORT`,
Postgres on `POSTGRES_PORT`, DuckDB in memory. Synthetic rows only (rule 9). What a mistake would
do, and the case that catches it:

- the dropped row's events left in the timeline, a kept row's taken with them, or any node or link
  of the dropped row withdrawn (`test_a_second_snapshot_missing_one_row_withdraws_its_events_and_the_revert_restores_them`);
- a row that comes back in a third snapshot skipped as kept, or creating its link again, or its
  events counted twice (`test_a_row_that_comes_back_is_loaded_again_once`);
- the refresh's revert restoring a row that came back (the same file's second case);
- a row dropped again after coming back moved aside a second time, a unique violation after the
  commit (`test_a_row_dropped_again_after_coming_back_is_left_in_place_in_words`)."""

from __future__ import annotations

import csv
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from schemas.analytics import EventFilter, EventListRequest
from schemas.domain import Handling
from services.api.config import PostgresConfig
from services.api.load_records import LedgerSink
from services.api.recipe_runs import RecipeRunStore
from services.api.studio_publish import run_published_recipe
from services.ingest.load_revert import RevertDeps, RevertRefused, revert
from services.ingest.watermark import RefreshRead

from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_revert_load import (
    Alerts,
    Audit,
    Held,
    Steps,
    WorkingSets,
    no_caches,
)
from tests.ingest.test_row_keys import LOADER, ONTOLOGY, ROWS, SCHEME, _published_draft

NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)
SOURCE = Handling(
    classification="OFFICIAL",
    handling_code="P",
    owning_unit="unit-1",
    originator="unit-1",
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

    def __init__(
        self, tmp_path: Path, runs: RecipeRunStore, graph: object, analytics: object
    ):
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
            self.runs,
            run_id,
            created_by=LOADER.id,
            investigation_id=self.case,
            started_at=NOW,
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
            EventListRequest(
                filter=EventFilter(investigation_scope=self.case), limit=100
            ),
            LOADER,
        )
        return int(page.total)

    async def revert(self, load_id: str) -> Any:
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
        return await revert(load_id, reverted_by="operator-1", deps=deps, now=NOW)


async def test_a_second_snapshot_missing_one_row_withdraws_its_events_and_the_revert_restores_them(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    async with (
        arcadedb_adapter(ONTOLOGY, SCHEME) as graph,
        duckdb_adapter([], SCHEME) as analytics,
    ):
        refresh = Refresh(tmp_path, runs, graph, analytics)
        first = await refresh.snapshot([A, B, C])
        assert first.rows_withdrawn == 0  # type: ignore[attr-defined]
        links = set(first.created_edge_ids)  # type: ignore[attr-defined]
        assert len(links) == 3
        assert await refresh.values() == {
            "SYN-1",
            "SYN-2",
            "SYN-3",
            "SYN-4",
            "SYN-5",
            "SYN-6",
        }
        assert await refresh.events() == 3

        second = await refresh.snapshot([A, C])

        assert second.rows_already_loaded == 2 and second.rows_withdrawn == 1  # type: ignore[attr-defined]
        # ADR-110 Amendment 15: the dropped row's own event goes; its nodes and link never do.
        assert (second.withdrawn_node_ids, second.withdrawn_edge_ids) == ([], [])  # type: ignore[attr-defined]
        assert await refresh.values() == {
            "SYN-1",
            "SYN-2",
            "SYN-3",
            "SYN-4",
            "SYN-5",
            "SYN-6",
        }
        assert {e.id for e in await graph.get_edges(sorted(links), LOADER)} == links
        assert await refresh.events() == 2, (
            "the dropped row's event leaves the timeline"
        )

        await refresh.revert(second.load_id)  # type: ignore[attr-defined]

        assert await refresh.values() == {
            "SYN-1",
            "SYN-2",
            "SYN-3",
            "SYN-4",
            "SYN-5",
            "SYN-6",
        }
        assert await refresh.events() == 3
        # Its key is kept again: the same snapshot run now withdraws it once more, not twice.
        again = await refresh.snapshot([A, C])
        assert again.rows_withdrawn == 1  # type: ignore[attr-defined]


async def test_a_row_that_comes_back_is_loaded_again_once(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    async with (
        arcadedb_adapter(ONTOLOGY, SCHEME) as graph,
        duckdb_adapter([], SCHEME) as analytics,
    ):
        refresh = Refresh(tmp_path, runs, graph, analytics)
        await refresh.snapshot([A, B, C])
        second = await refresh.snapshot([A, C])

        back = await refresh.snapshot([A, B, C])

        # Its nodes and link never left (Amendment 15): matched and merged into, not created.
        assert back.rows_already_loaded == 2 and back.nodes_created == 0  # type: ignore[attr-defined]
        assert (back.edges_created, back.created_edge_ids) == (0, [])  # type: ignore[attr-defined]
        assert await refresh.values() == {
            "SYN-1",
            "SYN-2",
            "SYN-3",
            "SYN-4",
            "SYN-5",
            "SYN-6",
        }
        assert await refresh.events() == 3, "each event held once"
        # The refresh that withdrew B is not reverted while B is loaded again.
        with pytest.raises(RevertRefused) as refused:
            await refresh.revert(second.load_id)  # type: ignore[attr-defined]
        assert [r.reason for r in refused.value.refusals] == [
            "withdrawn_rows_loaded_again"
        ]
        assert await refresh.events() == 3


async def test_a_row_dropped_again_after_coming_back_is_left_in_place_in_words(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    """ADR-110 Amendment 15, live: drop B, B comes back, drop B again. The third snapshot cannot
    move B's key aside a second time (the first withdrawal's entry stands), so B is left in place,
    its event too, and the run says so, where before it was a unique violation after the commit."""
    async with (
        arcadedb_adapter(ONTOLOGY, SCHEME) as graph,
        duckdb_adapter([], SCHEME) as analytics,
    ):
        refresh = Refresh(tmp_path, runs, graph, analytics)
        await refresh.snapshot([A, B, C])
        await refresh.snapshot([A, C])
        back = await refresh.snapshot([A, B, C])
        assert back.refresh_notes and "came back" in back.refresh_notes[0]  # type: ignore[attr-defined]
        assert await refresh.events() == 3

        again = await refresh.snapshot([A, C])

        assert (again.rows_withdrawn, again.rows_left_in_place) == (0, 1)  # type: ignore[attr-defined]
        assert (
            "had come back after an earlier refresh withdrew it"
            in again.refresh_notes[0]
        )  # type: ignore[attr-defined]
        assert await refresh.events() == 3, "B's new event stays"


async def test_a_returning_rows_load_reverts_and_the_chain_unwinds_live(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    """ADR-110 Amendment 16 through the real revert, on real ArcadeDB, the run ledger and DuckDB:
    B comes back and merges into its own link; its load reverts and the link is exactly as the
    refresh left it; then the refresh reverts (B's key and event back to the first load); then the
    first load reverts, and nothing of the file is left."""
    from tests.ingest.test_row_elements import _key

    async with (
        arcadedb_adapter(ONTOLOGY, SCHEME) as graph,
        duckdb_adapter([], SCHEME) as analytics,
    ):
        refresh = Refresh(tmp_path, runs, graph, analytics)
        first = await refresh.snapshot([A, B, C])
        second = await refresh.snapshot([A, C])
        (b_link,) = first.kept_row_elements[_key(B)].edge_ids  # type: ignore[attr-defined]
        after_the_refresh = await graph.read_link_state(b_link)
        back = await refresh.snapshot([A, B, C])
        assert [m.edge_id for m in back.own_key_merges] == [b_link]  # type: ignore[attr-defined]
        assert await refresh.events() == 3

        undone = await refresh.revert(back.load_id)  # type: ignore[attr-defined]
        assert [r.links_put_back for r in undone.reverted] == [1]
        assert await graph.read_link_state(b_link) == after_the_refresh, "exactly as it was"
        assert await refresh.events() == 2

        await refresh.revert(second.load_id)  # type: ignore[attr-defined]
        assert await refresh.events() == 3
        await refresh.revert(first.load_id)  # type: ignore[attr-defined]
        assert await refresh.values() == set() and await refresh.events() == 0


async def test_a_returning_rows_revert_is_refused_once_another_case_wrote_its_link_live(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    """ADR-110 Amendment 16, rule 3, live: another case's refresh of the same pair merges into the
    link after B came back (the raw adapter stamps no dataset, so the two share it). The returning
    load's revert is refused, nothing changes, and the words name no other case or load."""
    async with (
        arcadedb_adapter(ONTOLOGY, SCHEME) as graph,
        duckdb_adapter([], SCHEME) as analytics,
    ):
        ours = Refresh(tmp_path / "ours", runs, graph, analytics)
        theirs = Refresh(tmp_path / "theirs", runs, graph, analytics)
        await ours.snapshot([A, B, C])
        await ours.snapshot([A, C])
        back = await ours.snapshot([A, B, C])
        await theirs.snapshot([B])
        before = (await ours.values(), await ours.events())

        with pytest.raises(RevertRefused) as refused:
            await ours.revert(back.load_id)  # type: ignore[attr-defined]

        (refusal,) = refused.value.refusals
        assert (refusal.reason, refusal.count) == ("own_link_written_since", 1)
        assert theirs.case not in refusal.words()
        assert (await ours.values(), await ours.events()) == before, "nothing changed"
