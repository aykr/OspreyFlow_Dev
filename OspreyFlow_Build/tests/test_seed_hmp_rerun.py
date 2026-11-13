"""A rerun of the HMP seed never says "loaded" over events it did not load (rule 2; ADR-148
Amendment 14, both reviews of the seed path). The graph and the events are two writes: when the
first committed and the second failed (a ClickHouse password, a policy), a rerun finds the graph
"already here" and wrote no events, then exited 0, and `seed_poc` printed "done". It now asks
the case's own analytics store, through the port as the seed's principal, whether the HMP events
are there, and refuses in words when they are not (recreating them would mean writing the graph
twice). Run at `_run` itself, its stores stood in for: the graph a fake that says what is
already here, the analytics store a real DuckDB."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from scripts import seed_hmp_fixture

from adapters.analytics_duckdb.testing import duckdb_adapter
from demo_fixtures.hmp import generate_hmp_events
from ontology.handling import load_uk_le_scheme

SCOPE = "case-poc-1"


class _Graph:
    """Says whether the HMP pack and its network are here, as `find_node` would."""

    def __init__(self, present: bool) -> None:
        self.present = present

    async def find_node(self, *args: Any) -> Any:
        return {"id": "n"} if self.present else None

    async def apply_schema(self, *args: Any) -> None: ...


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    w = SimpleNamespace(present=True, store=None, fail_analytics=False)

    class _Client:
        def __init__(self, *a: Any) -> None: ...
        async def create_database_if_absent(self) -> None: ...
        async def aclose(self) -> None: ...

    async def scope_for(*a: Any, **k: Any) -> str:
        return SCOPE

    async def nothing(*a: Any, **k: Any) -> Any:
        return False

    @asynccontextmanager
    async def analytics(path: str, scheme: Any) -> AsyncIterator[Any]:
        if w.fail_analytics:
            raise ConnectionError("ClickHouse refused the password")
        yield w.store

    monkeypatch.setattr(seed_hmp_fixture, "ArcadeDBClient", _Client)
    monkeypatch.setattr(
        seed_hmp_fixture, "ArcadeDBConfig", SimpleNamespace(from_env=lambda db: None)
    )
    monkeypatch.setattr(seed_hmp_fixture, "GraphArcadeDBAdapter", lambda c, s: None)
    monkeypatch.setattr(
        seed_hmp_fixture, "stamping", lambda g, dataset: _Graph(w.present)
    )
    monkeypatch.setattr(seed_hmp_fixture, "scope_for", scope_for)
    monkeypatch.setattr(seed_hmp_fixture, "write_hmp_places", nothing)
    monkeypatch.setattr(seed_hmp_fixture, "report_ids_stored_twice", nothing)
    monkeypatch.setattr(seed_hmp_fixture, "seed_analytics", analytics)
    return w


async def _run() -> int:
    args = seed_hmp_fixture._parse_args(["--investigation-scope", SCOPE])
    return await seed_hmp_fixture._run(args)


async def test_a_rerun_over_a_graph_whose_events_were_lost_refuses_in_words(
    world, capsys
) -> None:  # type: ignore[no-untyped-def]
    scheme = load_uk_le_scheme()
    async with duckdb_adapter([], scheme) as store:
        world.store = store
        assert await _run() == 1
    said = capsys.readouterr()
    assert "HMP" in said.err and "events are not" in said.err and SCOPE in said.err
    assert "Loaded" not in said.out


async def test_a_rerun_over_a_graph_with_its_events_says_so_and_succeeds(
    world, capsys
) -> None:  # type: ignore[no-untyped-def]
    scheme = load_uk_le_scheme()
    async with duckdb_adapter(
        generate_hmp_events(investigation_scope=SCOPE), scheme
    ) as store:
        world.store = store
        assert await _run() == 0
    assert "already here" in capsys.readouterr().out


async def test_a_failure_between_the_graph_and_the_events_fails_the_run(world) -> None:  # type: ignore[no-untyped-def]
    """The first run: the graph written (here, as already present), then the analytics store
    refused. The run fails, and the rerun refuses rather than reporting nothing missing."""
    world.fail_analytics = True
    with pytest.raises(ConnectionError):
        await _run()
