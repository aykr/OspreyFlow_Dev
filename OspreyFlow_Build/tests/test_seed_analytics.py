"""Spec 08's seeds write their events to the deployment's own analytics store (ADR-148 Amendment 14,
the POC seed path): the one `OSPREY_ANALYTICS_ENGINE` names, opened by the Conduit's own opener.

Before, `seed_hmp_fixture` and `seed_scenarios` opened DuckDB by path whatever the deployment named,
so on a ClickHouse deployment (every `cloud-platform` one) the graph half arrived and the events
half went to a file in the seed's container, lost with it, while the seed printed "loaded" (rule
2). The cases here are each a plant at the real call site: the seeders' own `_run`, read as
written, and the opener they call, given the engine as a deployment's environment gives it.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from scripts import seed_analytics
from services.api import analytics_store

from ontology.handling import load_uk_le_scheme

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
#: Spec 08's seeds that write events (`seed_fixture_corp` writes the graph alone).
EVENT_SEEDS = ("seed_hmp_fixture", "seed_scenarios")


def _duckdb_imports(module: str) -> list[str]:
    """Every import of DuckDB in the module, in any form (`import duckdb`, `from duckdb import`)."""
    tree = ast.parse((CORE / "scripts" / f"{module}.py").read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] == "duckdb"]
        elif (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").split(".")[0] == "duckdb"
        ):
            found.append(f"from {node.module}")
    return found


def _calls(module: str) -> set[str]:
    tree = ast.parse((CORE / "scripts" / f"{module}.py").read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                out.add(f"{f.value.id}.{f.attr}")
            elif isinstance(f, ast.Name):
                out.add(f.id)
    return out


@pytest.mark.parametrize("module", EVENT_SEEDS)
def test_the_seed_opens_the_deployments_store_never_duckdb_by_path(module: str) -> None:
    calls = _calls(module)
    assert "duckdb.connect" not in calls, (
        f"{module} opens DuckDB itself, whatever the deployment names"
    )
    assert _duckdb_imports(module) == [], f"{module} imports DuckDB itself"
    assert "seed_analytics" in calls, (
        f"{module} does not write through the deployment's analytics store"
    )


@pytest.mark.parametrize("engine", ["duckdb", "clickhouse"])
async def test_the_store_is_the_one_the_deployment_names(
    engine: str, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    opened: list[tuple[str, str]] = []
    closed: list[bool] = []

    async def open_analytics(
        name: str, *, duckdb_path: str, handling_scheme: Any
    ) -> tuple[Any, Any]:
        opened.append((name, duckdb_path))

        async def close() -> None:
            closed.append(True)

        return object(), close

    monkeypatch.setattr(analytics_store, "open_analytics", open_analytics)
    monkeypatch.setenv("OSPREY_ANALYTICS_ENGINE", engine)
    path = str(tmp_path / "analytics.duckdb")
    async with seed_analytics.seed_analytics(path, load_uk_le_scheme()):
        pass
    assert opened == [(engine, path)] and closed == [True]


async def test_an_engine_the_conduit_does_not_know_is_refused_not_taken_for_duckdb(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OSPREY_ANALYTICS_ENGINE", "clikhouse")
    with pytest.raises(analytics_store.UnknownAnalyticsEngine):
        async with seed_analytics.seed_analytics(
            str(tmp_path / "a.duckdb"), load_uk_le_scheme()
        ):
            pass
    assert not (tmp_path / "a.duckdb").exists()


async def test_on_duckdb_the_events_land_in_the_deployments_own_file(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """The real opener, not a stand-in: on a DuckDB deployment the seed's events are in the file the
    Conduit reads (`ANALYTICS_DB_PATH`), read back through a fresh connection to it."""
    import duckdb

    from demo_fixtures.hmp import generate_hmp_events

    monkeypatch.setenv("OSPREY_ANALYTICS_ENGINE", "duckdb")
    path = tmp_path / "analytics.duckdb"
    events = generate_hmp_events(investigation_scope="case-1")[:5]
    async with seed_analytics.seed_analytics(
        str(path), load_uk_le_scheme()
    ) as analytics:
        await analytics.load_events(events)
    con = duckdb.connect(str(path))
    try:
        held = {r[0] for r in con.execute("SELECT event_id FROM events").fetchall()}
    finally:
        con.close()
    assert held == {e.event_id for e in events}


@pytest.mark.parametrize("engine", ["duckdb", "clickhouse"])
async def test_hmps_events_and_places_go_through_each_store(engine: str) -> None:
    """HMP's own event and place shapes through each store a deployment can name (ClickHouse's the
    live server beside `make test`'s stack, never a fake): its events loaded and read back by id,
    its places loaded and found (`seed_hmp_fixture`'s analytics half)."""
    from adapters.analytics_clickhouse.testing import clickhouse_adapter
    from adapters.analytics_duckdb.testing import duckdb_adapter
    from demo_fixtures.hmp import generate_hmp_events
    from demo_fixtures.hmp_network import geometry_records
    from schemas.analytics import EventFilter, EventListRequest
    from schemas.domain import Principal

    scheme = load_uk_le_scheme()
    reader = Principal(id="hmp-seed-worker", clearance="SECRET", org_unit="unit-1")
    events = generate_hmp_events(investigation_scope="case-1")[:50]
    ids = [e.event_id for e in events]
    opener = {"duckdb": duckdb_adapter, "clickhouse": clickhouse_adapter}[engine]
    async with opener(events, scheme) as analytics:
        request = EventListRequest(
            filter=EventFilter(investigation_scope="case-1", event_ids=ids), limit=200
        )
        listed = await analytics.list_events(request, reader)
        assert {e.event_id for e in listed.events} == set(ids)
        wanted = geometry_records()
        await analytics.load_geometries(wanted)
        refs = [r.geometry_ref for r in wanted]
        held = await analytics.get_geometries(refs, reader, version=1)
        assert {r.geometry_ref for r in held} == set(refs)
