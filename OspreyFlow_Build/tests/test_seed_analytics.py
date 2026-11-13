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
        async with seed_analytics.seed_analytics(str(tmp_path / "a.duckdb"), load_uk_le_scheme()):
            pass
    assert not (tmp_path / "a.duckdb").exists()
