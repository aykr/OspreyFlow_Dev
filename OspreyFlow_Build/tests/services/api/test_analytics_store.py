"""The Conduit opens the analytics store `components.analytics_engine` names (ADR-114 decision 9),
and refuses one it does not know in words rather than falling back to DuckDB — a cluster that
silently ran an in-process DuckDB per replica would give each Conduit its own events.

The ClickHouse half needs a live server and is in `tests/test_analytics_clickhouse.py`."""

from __future__ import annotations

from pathlib import Path

import pytest
from services.api.analytics_store import UnknownAnalyticsEngine, open_analytics

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from ontology.handling import load_uk_le_scheme


async def test_duckdb_is_opened_at_the_file_the_deployment_names(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "analytics.duckdb"
    analytics, close = await open_analytics(
        "duckdb", duckdb_path=str(path), handling_scheme=load_uk_le_scheme()
    )
    try:
        assert isinstance(analytics, AnalyticsDuckDBAdapter)
        assert path.exists()
    finally:
        await close()


@pytest.mark.parametrize("engine", ["", "clickhous", "sqlite", "DuckDB "])
async def test_an_engine_it_does_not_know_is_refused_in_words(engine: str, tmp_path: Path) -> None:
    with pytest.raises(UnknownAnalyticsEngine, match="duckdb, clickhouse"):
        await open_analytics(
            engine, duckdb_path=str(tmp_path / "a.duckdb"), handling_scheme=load_uk_le_scheme()
        )
