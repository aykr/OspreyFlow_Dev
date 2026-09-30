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
    """Stands in for ArcadeDB: keeps rows by type, answers the statements the clean-up sends, and
    can refuse chosen statement forms with the parser error the real server gave (seen on the
    owner's machine: `DELETE EDGE ...` is not accepted as a first word), so the test can see which
    forms are tried, in what order, and what each would delete."""

    def __init__(self, rows: dict[str, list[str]], *, parse_error_on: tuple[str, ...] = ()) -> None:
        self.rows = {k: list(v) for k, v in rows.items()}
        self.statements: list[str] = []
        self.stubborn = False
        self.parse_error_on = parse_error_on
        self.other_error_on: str | None = None
        self.record_missing_on: str | None = None

    def _maybe_fail(self, command: str) -> None:
        from adapters.graph_arcadedb.client import ArcadeDBError

        if self.other_error_on and command.startswith(self.other_error_on):
            raise ArcadeDBError("ArcadeDB error 500: disk full", status_code=500)
        if self.record_missing_on and command.startswith(self.record_missing_on):
            raise ArcadeDBError(
                "ArcadeDB error 404: Record #169:80 not found",
                status_code=404,
                exception_class="com.arcadedb.exception.RecordNotFoundException",
            )
        if any(command.startswith(p) for p in self.parse_error_on):
            raise ArcadeDBError(
                "ArcadeDB error 500: Encountered DELETE",
                status_code=500,
                exception_class="com.arcadedb.query.sql.parser.ParseException",
            )

    def _delete(self, name: str, start: str) -> int:
        matching = [i for i in self.rows.get(name, []) if i.startswith(start)]
        if not self.stubborn:
            self.rows[name] = [i for i in self.rows.get(name, []) if i not in matching]
        return len(matching)

    async def sql(self, command: str, **_: object) -> list[dict[str, object]]:
        import re

        self.statements.append(command)
        self._maybe_fail(command)
        truncate = re.match(r"TRUNCATE TYPE (\w+) UNSAFE$", command)
        if truncate:
            self.rows[truncate.group(1)] = []
            return [{"count": 0}]
        every = re.match(r"SELECT count\(\*\) AS n FROM (\w+)$", command)
        if every:
            return [{"n": len(self.rows.get(every.group(1), []))}]
        kind = re.search(r"(?:FROM|EDGE|VERTEX) (\w+)", command)
        prefix = re.search(r"LIKE '([^']*)%'", command)
        assert kind and prefix, command
        name, start = kind.group(1), prefix.group(1)
        if command.startswith("SELECT"):
            return [{"n": len([i for i in self.rows.get(name, []) if i.startswith(start)])}]
        return [{"count": self._delete(name, start)}]

    async def gremlin(self, command: str, **_: object) -> list[dict[str, object]]:
        import re

        self.statements.append(command)
        self._maybe_fail(command)
        label = re.search(r"hasLabel\('(\w+)'\)", command)
        prefix = re.search(r"startingWith\('([^']*)'\)", command)
        assert label and prefix and command.endswith(".drop()"), command
        self._delete(label.group(1), prefix.group(1))
        return []


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
    assert "TRANSACTED" in deletes[0] and "Endpoint" in deletes[1]
    assert all("LIKE 'paysim-" in s for s in deletes)


def test_a_clean_up_that_leaves_rows_behind_is_an_error_not_a_success() -> None:
    """Catches carrying on to a fresh load on top of leftovers (which is what double-counted)."""
    client = FakeClient({"Endpoint": ["paysim-acct-1"], "TRANSACTED": ["paysim-tx-1"]})
    client.stubborn = True
    with pytest.raises(seed_support.CleanUpIncomplete, match="left"):
        _clear(client)


def test_an_empty_graph_is_cleared_without_fuss() -> None:
    assert _clear(FakeClient({})) == (0, 0)


def test_when_the_parser_refuses_one_delete_form_the_next_is_tried_and_all_are_prefix_scoped() -> (
    None
):
    """Seen: ArcadeDB rejected `DELETE EDGE ...` with a ParseException. Catches a clean-up that
    stops at the first form the server does not accept, and a fallback form that is not scoped by
    the id prefix (which would wipe another dataset)."""
    client = FakeClient(
        {"Endpoint": ["paysim-acct-1", "enron-ep-1"], "TRANSACTED": ["paysim-tx-1", "other-tx"]},
        parse_error_on=("DELETE EDGE", "DELETE VERTEX"),
    )
    assert _clear(client) == (1, 1)
    assert client.rows == {"Endpoint": ["enron-ep-1"], "TRANSACTED": ["other-tx"]}
    deletes = [s for s in client.statements if s.startswith(("DELETE", "g."))]
    assert all("paysim-" in s for s in deletes)


def test_the_gremlin_drop_is_the_last_resort_and_is_scoped_and_labelled() -> None:
    """If neither SQL form parses, the Gremlin bridge the adapter already uses is tried, by label
    and id prefix. Catches an unscoped `g.E().drop()`."""
    client = FakeClient(
        {"Endpoint": ["paysim-acct-1", "enron-ep-1"], "TRANSACTED": ["paysim-tx-1"]},
        parse_error_on=("DELETE",),
    )
    assert _clear(client) == (1, 1)
    drops = [s for s in client.statements if s.startswith("g.")]
    assert len(drops) == 2
    assert all(".hasLabel(" in s and "startingWith('paysim-" in s for s in drops)
    assert client.rows["Endpoint"] == ["enron-ep-1"]


def test_an_error_that_is_not_a_parse_error_is_raised_not_worked_around() -> None:
    """Catches masking a real failure (a full disk, a lock) by trying the next form."""
    from adapters.graph_arcadedb.client import ArcadeDBError

    client = FakeClient({"Endpoint": ["paysim-acct-1"], "TRANSACTED": ["paysim-tx-1"]})
    client.other_error_on = "DELETE"
    with pytest.raises(ArcadeDBError, match="disk full"):
        _clear(client)
    assert sum(1 for s in client.statements if s.startswith("DELETE")) == 1


def test_when_no_form_is_accepted_the_error_names_every_form_tried() -> None:
    """Catches a failure that leaves the owner unable to tell what was attempted."""
    client = FakeClient(
        {"Endpoint": ["paysim-acct-1"], "TRANSACTED": ["paysim-tx-1"]},
        parse_error_on=("DELETE", "g."),
    )
    with pytest.raises(seed_support.CleanUpIncomplete, match="DELETE FROM.*DELETE EDGE.*drop"):
        _clear(client)


def test_a_missing_record_during_delete_falls_back_to_truncating_types_that_hold_only_this_seed() -> (
    None
):
    """Seen: DELETE FROM failed with 404 `Record #169:80 not found` after interrupted loads. When
    every row in both types is this seed's, the types are truncated, edges before vertices."""
    client = FakeClient(
        {"Endpoint": ["paysim-acct-1", "paysim-acct-2"], "TRANSACTED": ["paysim-tx-1"]}
    )
    client.record_missing_on = "DELETE"
    assert _clear(client) == (2, 1)
    truncates = [s for s in client.statements if s.startswith("TRUNCATE")]
    assert truncates == ["TRUNCATE TYPE TRANSACTED UNSAFE", "TRUNCATE TYPE Endpoint UNSAFE"]
    assert client.rows == {"Endpoint": [], "TRANSACTED": []}


def test_the_truncate_is_refused_when_a_type_holds_rows_that_are_not_this_seeds() -> None:
    """Catches wiping another dataset's accounts (Enron shares the Endpoint type)."""
    client = FakeClient(
        {"Endpoint": ["paysim-acct-1", "enron-ep-1"], "TRANSACTED": ["paysim-tx-1"]}
    )
    client.record_missing_on = "DELETE"
    with pytest.raises(seed_support.CleanUpIncomplete, match="not this seed"):
        _clear(client)
    assert not [s for s in client.statements if s.startswith("TRUNCATE")]
    assert client.rows["Endpoint"] == ["paysim-acct-1", "enron-ep-1"]


def test_a_normal_clean_up_never_truncates() -> None:
    client = FakeClient({"Endpoint": ["paysim-acct-1"], "TRANSACTED": ["paysim-tx-1"]})
    _clear(client)
    assert not [s for s in client.statements if s.startswith("TRUNCATE")]


# --- reading what the graph holds, without changing it (ADR-055 Amendment 6) ---


class ProbeClient:
    def __init__(self, fail_on: str | None = None) -> None:
        self.statements: list[str] = []
        self.fail_on = fail_on

    async def sql(self, command: str, **_: object) -> list[dict[str, object]]:
        from adapters.graph_arcadedb.client import ArcadeDBError

        self.statements.append(command)
        if self.fail_on and self.fail_on in command:
            raise ArcadeDBError(
                "ArcadeDB error 404: Record #169:80 not found",
                status_code=404,
                exception_class="com.arcadedb.exception.RecordNotFoundException",
            )
        return [{"n": 7}]


def _inspect(client: ProbeClient) -> list[str]:
    return asyncio.run(
        seed_support.inspect_graph(
            client,  # type: ignore[arg-type]
            node_type="Endpoint",
            node_prefix="paysim-acct-",
            edge_type="TRANSACTED",
            edge_prefix="paysim-tx-",
            record="#169:80",
        )
    )


def test_inspect_only_ever_sends_selects() -> None:
    """The point of the mode is that it cannot change anything. Catches a probe that writes."""
    client = ProbeClient()
    _inspect(client)
    assert client.statements and all(s.startswith("SELECT") for s in client.statements)


def test_inspect_reports_each_probe_and_carries_on_past_a_failing_one() -> None:
    """Catches one unreadable record hiding everything else: the failure is itself the evidence."""
    lines = _inspect(ProbeClient(fail_on="#169:80"))
    text = "\n".join(lines)
    assert "#169:80" in text and "not found" in text
    assert "paysim-tx-" in text and "paysim-acct-" in text
    assert text.count("7") >= 3
