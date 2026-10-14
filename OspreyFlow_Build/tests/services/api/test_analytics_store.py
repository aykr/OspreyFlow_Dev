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


# --- a replicated ClickHouse (`spec/05_DEPLOYMENT.md` §3b) ------------------------------------
#
# Measured on two `clickhouse-server:25.8.33.6` nodes and three Keepers, 14 October 2026: in a
# `Replicated` database a table made `ENGINE = MergeTree` has its definition carried to every node
# but its rows kept on the one that took them (an insert on one node, none on the other), while
# `ReplicatedMergeTree` carried an insert across within 50 ms. The cluster's own server setting
# refuses a plain `MergeTree` there; these cases pin what the Conduit asks for.


def _statements_sent(monkeypatch: pytest.MonkeyPatch, **env: str) -> list[str]:
    import httpx
    from services.api import analytics_store

    for name in ("CLICKHOUSE_CLUSTER", "CLICKHOUSE_DATABASE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request.content.decode())
        return httpx.Response(200, text="")

    real = analytics_store.ClickHouseClient
    monkeypatch.setattr(
        analytics_store,
        "ClickHouseClient",
        lambda settings: real(settings, httpx.AsyncClient(transport=httpx.MockTransport(answer))),
    )
    return sent


async def test_a_cluster_makes_its_database_replicated_on_every_node(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sent = _statements_sent(monkeypatch, CLICKHOUSE_CLUSTER="osprey")
    _, close = await open_analytics(
        "clickhouse", duckdb_path=str(tmp_path / "a.duckdb"), handling_scheme=load_uk_le_scheme()
    )
    await close()
    assert sent[0] == (
        "CREATE DATABASE IF NOT EXISTS ospreyflow ON CLUSTER osprey ENGINE = "
        "Replicated('/clickhouse/databases/ospreyflow', '{shard}', '{replica}')"
    )
    tables = [s for s in sent if s.lstrip().startswith("CREATE TABLE")]
    assert len(tables) == 2
    assert all("ENGINE = ReplicatedMergeTree" in s for s in tables)


async def test_a_single_server_keeps_plain_tables_in_a_plain_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sent = _statements_sent(monkeypatch)
    _, close = await open_analytics(
        "clickhouse", duckdb_path=str(tmp_path / "a.duckdb"), handling_scheme=load_uk_le_scheme()
    )
    await close()
    assert sent[0] == "CREATE DATABASE IF NOT EXISTS ospreyflow"
    tables = [s for s in sent if s.lstrip().startswith("CREATE TABLE")]
    assert len(tables) == 2
    assert all("ENGINE = MergeTree" in s and "Replicated" not in s for s in tables)


async def test_a_cluster_name_that_is_not_a_plain_name_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sent = _statements_sent(monkeypatch, CLICKHOUSE_CLUSTER="osprey ENGINE = Memory --")
    with pytest.raises(ValueError, match="CLICKHOUSE_CLUSTER"):
        await open_analytics(
            "clickhouse",
            duckdb_path=str(tmp_path / "a.duckdb"),
            handling_scheme=load_uk_le_scheme(),
        )
    assert sent == []
