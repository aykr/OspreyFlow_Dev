"""ADR-110 Amendment 6 point 1, an incremental refresh, live end to end through the path a source
refresh takes (`run_published_recipe` with the source's `RefreshRead`, a `LedgerSink` over the real
run ledger): ArcadeDB on `ARCADEDB_HTTP_PORT`, Postgres on `POSTGRES_PORT`, DuckDB in memory.
Synthetic rows only (rule 9); the watermark column is `paid_at`.

What a mistake would do, and the case that catches it:

- the watermark ignored, so a row at or below it (here a late correction with a new key) is loaded
  (`test_a_poll_loads_only_the_rows_past_the_watermark`);
- the watermark not kept with the record, so the next poll reads the whole file again (the same
  case: its rows below are counted, not deduplicated);
- a load reverted while a later poll read past it, its rows then never read again
  (`test_a_load_a_later_poll_read_past_is_not_reverted_and_the_last_one_reads_again`);
- a reverted poll's watermark kept, so its rows are not read again (the same case)."""

from __future__ import annotations

from pathlib import Path

import pytest
from services.api.recipe_runs import RecipeRunStore
from services.ingest.load_revert import RevertRefused
from services.ingest.watermark import RefreshRead

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_row_keys import LOADER, ONTOLOGY, SCHEME, _row
from tests.services.api.test_source_refresh_snapshot_live import Refresh, runs

__all__ = ["runs"]  # the fixture, used by name

READ = RefreshRead(source_id="src-1", mode="incremental", watermark_column="paid_at")
A, B, C = _row("SYN-1", "SYN-2", 1), _row("SYN-3", "SYN-4", 2), _row("SYN-5", "SYN-6", 3)
#: A late correction of B: the same time, another payee, so another key, at the watermark.
B_LATE = _row("SYN-3", "SYN-9", 2)


async def _late_payee(refresh: Refresh) -> object:
    return await refresh.graph.find_node(  # type: ignore[attr-defined]
        "Endpoint", "value_normalised", "SYN-9", LOADER
    )


async def test_a_poll_loads_only_the_rows_past_the_watermark(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph, duckdb_adapter([], SCHEME) as analytics:
        refresh = Refresh(tmp_path, runs, graph, analytics)
        first = await refresh.snapshot([A, B], READ)
        assert first.rows_below_watermark == 0 and first.nodes_created == 4  # type: ignore[attr-defined]
        assert first.watermark.value == B["paid_at"]  # type: ignore[attr-defined]

        second = await refresh.snapshot([A, B, B_LATE, C], READ)

        assert second.rows_read == 1 and second.rows_below_watermark == 3  # type: ignore[attr-defined]
        assert second.rows_already_loaded == 0, "below the watermark is not read, not deduplicated"  # type: ignore[attr-defined]
        assert second.nodes_created == 2  # type: ignore[attr-defined]
        assert await _late_payee(refresh) is None, "a row at the watermark is not loaded"
        assert await refresh.values() == {"SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5", "SYN-6"}
        assert await refresh.events() == 3
        assert second.watermark.value == C["paid_at"]  # type: ignore[attr-defined]
        assert second.refresh_notes == [  # type: ignore[attr-defined]
            "3 rows at or below the watermark (paid_at) were not read"
        ]


async def test_a_load_a_later_poll_read_past_is_not_reverted_and_the_last_one_reads_again(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph, duckdb_adapter([], SCHEME) as analytics:
        refresh = Refresh(tmp_path, runs, graph, analytics)
        first = await refresh.snapshot([A, B], READ)
        second = await refresh.snapshot([A, B, C], READ)

        with pytest.raises(RevertRefused) as refused:
            await refresh.revert(first.load_id)  # type: ignore[attr-defined]
        assert [r.reason for r in refused.value.refusals] == ["read_past_by_a_later_refresh"]

        await refresh.revert(second.load_id)  # type: ignore[attr-defined]
        assert await refresh.values() == {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}
        assert await refresh.events() == 2

        again = await refresh.snapshot([A, B, C], READ)
        assert again.rows_read == 1 and again.nodes_created == 2  # type: ignore[attr-defined]
        assert await refresh.values() == {"SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5", "SYN-6"}
        assert await refresh.events() == 3, "each event held once"
