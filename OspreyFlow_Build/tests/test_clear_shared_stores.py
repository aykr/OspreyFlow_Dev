"""Clearing the shared stores once the PaySim vault is verified (ADR-056 Amendment 16, stage 0b).

The owner's ruling (Amendment 1): after the vault is verified, drop the shared `ospreyflow` graph
database and the shared analytics events and create them clean; case records stay. It deletes data
that cannot be got back except by reloading, so it is built to be hard to run by accident: it
refuses unless the vault is verified (a graph, no id stored twice, events), it first reports exactly
what it would delete, and it deletes only when the owner passes back those exact counts. Each test
names what it would catch.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import pytest
from scripts import clear_shared_stores as css


class Graph:
    def __init__(self, vertices: int = 100, edges: int = 80, *, leaves: tuple[int, int] = (0, 0)):
        self.vertices, self.edges = vertices, edges
        self.leaves = leaves
        self.reset_calls = 0

    async def counts(self) -> tuple[int, int]:
        return self.vertices, self.edges

    async def reset(self) -> None:
        self.reset_calls += 1
        self.vertices, self.edges = self.leaves


class Events:
    def __init__(self, n: int = 5000, *, leaves: int = 0) -> None:
        self.n, self.leaves = n, leaves
        self.clear_calls = 0

    def count(self) -> int:
        return self.n

    def clear(self) -> None:
        self.clear_calls += 1
        self.n = self.leaves


def _go(
    graph: Graph, events: Events, *, problems: Sequence[str] = (), confirm: str | None = None
) -> tuple[int, str]:
    lines: list[str] = []
    code = asyncio.run(
        css.clear_shared(
            graph,
            events,
            vault_problems=list(problems),
            confirm=confirm,
            say=lines.append,
        )
    )
    return code, "\n".join(lines)


def test_nothing_is_cleared_while_the_vault_has_a_problem_and_each_problem_is_named() -> None:
    """Catches wiping the only copy of the data because the new copy was never checked."""
    graph, events = Graph(), Events()
    code, text = _go(graph, events, problems=["the vault has no events"], confirm="100:80:5000")
    assert code == 2 and "the vault has no events" in text
    assert graph.reset_calls == 0 and events.clear_calls == 0


def test_without_confirmation_it_only_reports_the_counts_and_how_to_confirm_them() -> None:
    """Catches a clear that runs on the first command, and a report without the way forward."""
    graph, events = Graph(), Events()
    code, text = _go(graph, events)
    assert code == 0 and graph.reset_calls == 0 and events.clear_calls == 0
    assert "100 vertices" in text and "80 edges" in text and "5,000 events" in text
    assert "--confirm 100:80:5000" in text


def test_a_confirmation_that_does_not_match_the_counts_deletes_nothing() -> None:
    """Catches a clear that proceeds on a stale or mistyped confirmation: the stores changed, or
    the owner never saw these numbers."""
    graph, events = Graph(), Events()
    code, text = _go(graph, events, confirm="100:80:4999")
    assert code == 3 and graph.reset_calls == 0 and events.clear_calls == 0
    assert "100:80:5000" in text


def test_the_matching_confirmation_clears_both_stores_and_checks_they_are_empty() -> None:
    graph, events = Graph(), Events()
    code, text = _go(graph, events, confirm="100:80:5000")
    assert code == 0 and graph.reset_calls == 1 and events.clear_calls == 1
    assert (graph.vertices, graph.edges, events.n) == (0, 0, 0)
    assert "cleared" in text


def test_a_store_that_is_not_empty_afterwards_is_reported_as_a_failure() -> None:
    """Catches claiming success after a clear that did not clear (a drop that quietly failed)."""
    graph, events = Graph(leaves=(3, 1)), Events()
    code, text = _go(graph, events, confirm="100:80:5000")
    assert code == 4 and "not empty" in text


def test_the_database_it_clears_can_never_be_a_vaults() -> None:
    """Catches pointing the clear at a vault by mistake (an environment variable, a typo)."""
    css.check_shared_database("ospreyflow")
    with pytest.raises(ValueError, match="vault"):
        css.check_shared_database("vault_paysim")


class Sql:
    def __init__(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        self.rows = rows

    async def sql(self, command: str, **_: object) -> list[dict[str, Any]]:
        for key, value in self.rows.items():
            if key in command:
                return value
        return []

    async def gremlin(self, command: str, **_: object) -> list[dict[str, Any]]:
        return []


def _problems(
    *, accounts: int = 10, transactions: int = 8, twice: int = 0, events: int = 9
) -> list[str]:
    client = Sql(
        {
            "paysim-acct-": [{"n": accounts}],
            "paysim-tx-%'": [{"n": transactions}],
            "GROUP BY id": [{"id": f"paysim-tx-{i}", "n": 2} for i in range(twice)],
        }
    )
    return asyncio.run(
        css.vault_problems(
            client,
            node_type="Endpoint",
            edge_type="TRANSACTED",
            events=Events(events),
        )
    )


def test_a_good_vault_has_no_problems() -> None:
    assert _problems() == []


def test_each_way_the_vault_can_be_unready_is_a_named_problem() -> None:
    """Catches a verification that passes an empty graph, a graph with stray records (which must be
    repaired first, or the clean copy is not clean), or a vault with no events."""
    assert any("no accounts" in p for p in _problems(accounts=0))
    assert any("no transactions" in p for p in _problems(transactions=0))
    assert any("stored more than once" in p and "repair" in p for p in _problems(twice=2))
    assert any("no events" in p for p in _problems(events=0))


def test_the_events_store_counts_and_clears_only_the_events_table(tmp_path: Path) -> None:
    """Catches a clear that drops other tables in the file (geometries) or leaves the events."""
    path = tmp_path / "analytics.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE events (id VARCHAR)")
    con.execute("INSERT INTO events VALUES ('a'), ('b'), ('c')")
    con.execute("CREATE TABLE geometries (id VARCHAR)")
    con.execute("INSERT INTO geometries VALUES ('g')")
    con.close()
    store = css.DuckEvents(path)
    assert store.count() == 3
    store.clear()
    assert store.count() == 0
    con = duckdb.connect(str(path), read_only=True)
    assert con.execute("SELECT count(*) FROM geometries").fetchone() == (1,)
    # The table itself is still there, empty: the Conduit finds it as it left it.
    assert con.execute("SELECT count(*) FROM events").fetchone() == (0,)
    con.close()


def test_a_missing_events_file_or_table_counts_as_no_events_and_is_not_created(
    tmp_path: Path,
) -> None:
    """Catches a count that creates the file it was only meant to read."""
    path = tmp_path / "nothing.duckdb"
    assert css.DuckEvents(path).count() == 0
    assert not path.exists()
