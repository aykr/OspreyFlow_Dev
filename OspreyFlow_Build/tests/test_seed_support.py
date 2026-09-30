"""What every dataset seed shares: progress while writing the graph, and refusing to load events
twice (ADR-055 Amendment 3). Seen: a PaySim run was interrupted mid-graph after hours; a plain
re-run would have refused on the half-written graph, and, had it not, would have doubled the events
(the events load is an INSERT). Each test names what it catches.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import duckdb
import pytest
from scripts import seed_support


class FakeGraph:
    def __init__(self) -> None:
        self.nodes = 0
        self.edges = 0
        self.fail_on_edges = False

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None: ...

    async def rollback_transaction(self, tx: str) -> None:
        self.rolled_back = True

    async def upsert_nodes(self, nodes: list[object], tx: str) -> list[str]:
        self.nodes += len(nodes)
        return []

    async def upsert_edges(self, edges: list[object], tx: str) -> list[str]:
        if self.fail_on_edges:
            raise RuntimeError("the graph went away")
        self.edges += len(edges)
        return []


def _write(graph: FakeGraph, n: int, e: int, **kw: object) -> None:
    asyncio.run(
        seed_support.write_graph(
            graph,  # type: ignore[arg-type]
            list(range(n)),  # type: ignore[arg-type]
            list(range(e)),  # type: ignore[arg-type]
            chunk=40,
            nouns=("accounts", "transactions"),
            **kw,  # type: ignore[arg-type]
        )
    )


def test_every_node_and_edge_is_written_in_batches_and_progress_is_printed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catches a silent write (five hours with one line of output) and a dropped final batch."""
    graph = FakeGraph()
    _write(graph, 241, 121)
    shown = capsys.readouterr().out
    assert (graph.nodes, graph.edges) == (241, 121)
    assert "241 of 241 accounts written" in shown
    assert "121 of 121 transactions written" in shown


def test_a_failing_batch_is_rolled_back_and_the_error_is_not_swallowed() -> None:
    """Catches a half-applied batch, and an error that lets the run carry on as if it worked."""
    graph = FakeGraph()
    graph.fail_on_edges = True
    with pytest.raises(RuntimeError, match="went away"):
        _write(graph, 10, 10)
    assert graph.rolled_back is True


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "a.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE events (event_id VARCHAR, investigation_scope VARCHAR)")
    con.execute("INSERT INTO events VALUES ('e1', 'case-a')")
    con.close()
    return path


def test_events_already_in_a_case_are_detected_and_other_cases_do_not_count(
    tmp_path: Path,
) -> None:
    """Catches a second load doubling a case's events, and a check that trips on someone else's."""
    path = _db(tmp_path)
    assert seed_support.events_already_loaded(path, "case-a") is True
    assert seed_support.events_already_loaded(path, "case-b") is False


def test_a_missing_analytics_file_or_table_means_no_events_yet(tmp_path: Path) -> None:
    """Catches the check crashing on a first-ever run."""
    assert seed_support.events_already_loaded(tmp_path / "none.duckdb", "case-a") is False
    empty = tmp_path / "empty.duckdb"
    duckdb.connect(str(empty)).close()
    assert seed_support.events_already_loaded(empty, "case-a") is False


# --- replacing a seed's own graph rows (ADR-055 Amendment 4) ---


class FakeClient:
    """Stands in for ArcadeDB's SQL endpoint: keeps rows by type and answers the three statements
    the clean-up sends, so the test can see exactly what would be deleted."""

    def __init__(self, rows: dict[str, list[str]]) -> None:
        self.rows = {k: list(v) for k, v in rows.items()}
        self.statements: list[str] = []
        self.stubborn = False

    async def sql(self, command: str, **_: object) -> list[dict[str, object]]:
        import re

        self.statements.append(command)
        kind = re.search(r"(?:FROM|EDGE|VERTEX) (\w+)", command)
        prefix = re.search(r"LIKE '([^']*)%'", command)
        assert kind and prefix, command
        name, start = kind.group(1), prefix.group(1)
        matching = [i for i in self.rows.get(name, []) if i.startswith(start)]
        if command.startswith("SELECT"):
            return [{"n": len(matching)}]
        if not self.stubborn:
            self.rows[name] = [i for i in self.rows.get(name, []) if i not in matching]
        return [{"count": len(matching)}]


def _clear(client: FakeClient) -> tuple[int, int]:
    return asyncio.run(
        seed_support.clear_seeded_graph(
            client,  # type: ignore[arg-type]
            node_type="Endpoint",
            node_prefix="paysim-acct-",
            edge_type="TRANSACTED",
            edge_prefix="paysim-tx-",
        )
    )


def test_only_rows_with_the_seeds_own_id_prefix_are_deleted_and_the_counts_are_returned() -> None:
    """Catches a clean-up that would delete another dataset's accounts or transactions (the
    Endpoint and edge types are shared with Enron and any later demo)."""
    client = FakeClient(
        {
            "Endpoint": ["paysim-acct-1", "paysim-acct-2", "enron-ep-1"],
            "TRANSACTED": ["paysim-tx-1", "other-tx-9"],
        }
    )
    assert _clear(client) == (2, 1)
    assert client.rows["Endpoint"] == ["enron-ep-1"]
    assert client.rows["TRANSACTED"] == ["other-tx-9"]


def test_transactions_are_deleted_before_accounts_and_every_delete_is_scoped_by_prefix() -> None:
    """Catches an unscoped `DELETE` (a whole type wiped) and the wrong order."""
    client = FakeClient({"Endpoint": ["paysim-acct-1"], "TRANSACTED": ["paysim-tx-1"]})
    _clear(client)
    deletes = [s for s in client.statements if s.startswith("DELETE")]
    assert deletes[0].startswith("DELETE EDGE") and deletes[1].startswith("DELETE VERTEX")
    assert all("LIKE 'paysim-" in s for s in deletes)


def test_a_clean_up_that_leaves_rows_behind_is_an_error_not_a_success() -> None:
    """Catches carrying on to a fresh load on top of leftovers (which is what double-counted)."""
    client = FakeClient({"Endpoint": ["paysim-acct-1"], "TRANSACTED": ["paysim-tx-1"]})
    client.stubborn = True
    with pytest.raises(seed_support.CleanUpIncomplete, match="left"):
        _clear(client)


def test_an_empty_graph_is_cleared_without_fuss() -> None:
    assert _clear(FakeClient({})) == (0, 0)
