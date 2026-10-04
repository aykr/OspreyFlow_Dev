"""What every dataset seed shares: progress while writing the graph, and refusing to load events
twice (ADR-055 Amendment 3). Seen: a PaySim run was interrupted mid-graph after hours; a plain
re-run would have refused on the half-written graph, and, had it not, would have doubled the events
(the events load is an INSERT). Each test names what it catches.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import duckdb
import httpx
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


def test_each_committed_batch_is_reported_with_its_position() -> None:
    """Seen: eight transactions were stored twice and nothing said which batch each came from. A
    reproduction needs to line a duplicate up with the batch that wrote it, and with a commit the
    client replayed during that batch. Catches a hook that is never called, called before the
    commit, or given a position counted across both kinds of item."""
    graph = FakeGraph()
    seen: list[tuple[str, int]] = []
    _write(graph, 81, 81, on_batch=lambda noun, index: seen.append((noun, index)))
    assert seen == [("accounts", 0), ("accounts", 1), ("accounts", 2)] + [
        ("transactions", 0),
        ("transactions", 1),
        ("transactions", 2),
    ]


def test_a_batch_that_fails_is_not_reported_as_written() -> None:
    graph = FakeGraph()
    graph.fail_on_edges = True
    seen: list[tuple[str, int]] = []
    with pytest.raises(RuntimeError):
        _write(graph, 40, 40, on_batch=lambda noun, index: seen.append((noun, index)))
    assert seen == [("accounts", 0)]


def test_a_hook_that_awaits_finishes_before_the_next_batch_starts() -> None:
    """The reproduction checks the database after each commit, which is a query and so must be
    awaited. Catches a hook whose coroutine is created and dropped (never run, with a warning) or
    run concurrently with the next batch, which would let a check see a later batch's writes."""
    events: list[str] = []

    class Ordered(FakeGraph):
        async def upsert_edges(self, edges: list[object], tx: str) -> list[str]:
            events.append("write")
            return await super().upsert_edges(edges, tx)

    async def check(noun: str, index: int) -> None:
        if noun == "transactions":
            events.append(f"check {index}")
            await asyncio.sleep(0)
            events.append(f"checked {index}")

    _write(Ordered(), 0, 81, on_batch=check)
    assert events == [
        "write", "check 0", "checked 0",
        "write", "check 1", "checked 1",
        "write", "check 2", "checked 2",
    ]  # fmt: skip


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


def test_a_cases_own_events_can_be_deleted_and_nobody_elses_are_touched(tmp_path: Path) -> None:
    """ADR-089: a loader that changes what an event carries (longer excerpts) needs the case's
    events replaced, not doubled and not refused for ever. The deleter removes that case's rows
    only and says how many."""
    path = _db(tmp_path)
    con = duckdb.connect(str(path))
    con.execute("INSERT INTO events VALUES ('e2', 'case-a'), ('e3', 'case-b')")
    con.close()
    assert seed_support.delete_case_events(path, "case-a") == 2
    assert seed_support.events_already_loaded(path, "case-a") is False
    assert seed_support.events_already_loaded(path, "case-b") is True
    # A second call finds nothing, and a missing file or table is nothing to delete, not a crash.
    assert seed_support.delete_case_events(path, "case-a") == 0
    assert seed_support.delete_case_events(tmp_path / "none.duckdb", "case-a") == 0
    empty = tmp_path / "empty.duckdb"
    duckdb.connect(str(empty)).close()
    assert seed_support.delete_case_events(empty, "case-a") == 0


def test_a_missing_analytics_file_or_table_means_no_events_yet(tmp_path: Path) -> None:
    """Catches the check crashing on a first-ever run."""
    assert (
        seed_support.events_already_loaded(tmp_path / "none.duckdb", "case-a") is False
    )
    empty = tmp_path / "empty.duckdb"
    duckdb.connect(str(empty)).close()
    assert seed_support.events_already_loaded(empty, "case-a") is False


# --- replacing a seed's own graph rows (ADR-055 Amendment 4) ---


class FakeClient:
    """Stands in for ArcadeDB: keeps rows by type, answers the statements the clean-up sends, and
    can refuse chosen statement forms with the parser error the real server gave (seen on the
    owner's machine: `DELETE EDGE ...` is not accepted as a first word), so the test can see which
    forms are tried, in what order, and what each would delete."""

    def __init__(
        self, rows: dict[str, list[str]], *, parse_error_on: tuple[str, ...] = ()
    ) -> None:
        self.rows = {k: list(v) for k, v in rows.items()}
        self.statements: list[str] = []
        self.stubborn = False
        self.parse_error_on = parse_error_on
        self.other_error_on: str | None = None
        self.record_missing_on: str | None = None
        self.truncate_times_out = False
        self.empties_after_polls = 0

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
            if self.truncate_times_out:
                # The server carries on emptying after the client gives up.
                self.pending = truncate.group(1)
                raise httpx.ReadTimeout("read timed out")
            self.rows[truncate.group(1)] = []
            return [{"count": 0}]
        every = re.match(r"SELECT count\(\*\) AS n FROM (\w+)$", command)
        if every:
            name = every.group(1)
            if getattr(self, "pending", None) == name:
                if self.empties_after_polls > 0:
                    self.empties_after_polls -= 1
                    return [{"n": max(len(self.rows.get(name, [])), 1)}]
                self.rows[name] = []
                self.pending = None
            return [{"n": len(self.rows.get(name, []))}]
        kind = re.search(r"(?:FROM|EDGE|VERTEX) (\w+)", command)
        prefix = re.search(r"LIKE '([^']*)%'", command)
        assert kind and prefix, command
        name, start = kind.group(1), prefix.group(1)
        if command.startswith("SELECT"):
            return [
                {"n": len([i for i in self.rows.get(name, []) if i.startswith(start)])}
            ]
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


async def _no_sleep(_: float) -> None:
    return None


def _clear(client: FakeClient, *, wait_seconds: float = 1800.0) -> tuple[int, int]:
    return asyncio.run(
        seed_support.clear_seeded_graph(
            client,  # type: ignore[arg-type]
            say=lambda _: None,
            sleep=_no_sleep,
            wait_seconds=wait_seconds,
            node_type="Endpoint",
            node_prefix="paysim-acct-",
            edge_type="TRANSACTED",
            edge_prefix="paysim-tx-",
        )
    )


def test_only_rows_with_the_seeds_own_id_prefix_are_deleted_and_the_counts_are_returned() -> (
    None
):
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


def test_transactions_are_deleted_before_accounts_and_every_delete_is_scoped_by_prefix() -> (
    None
):
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
        {
            "Endpoint": ["paysim-acct-1", "enron-ep-1"],
            "TRANSACTED": ["paysim-tx-1", "other-tx"],
        },
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
    with pytest.raises(
        seed_support.CleanUpIncomplete, match="DELETE FROM.*DELETE EDGE.*drop"
    ):
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
    assert truncates == [
        "TRUNCATE TYPE TRANSACTED UNSAFE",
        "TRUNCATE TYPE Endpoint UNSAFE",
    ]
    assert client.rows == {"Endpoint": [], "TRANSACTED": []}


def test_the_truncate_is_refused_when_a_type_holds_rows_that_are_not_this_seeds() -> (
    None
):
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


def test_a_truncate_the_client_gives_up_on_is_waited_for_not_treated_as_a_failure() -> (
    None
):
    """Seen: the 30-second client timeout fired on TRUNCATE while ArcadeDB was still emptying the
    type. Catches a clean-up that aborts (leaving a half-emptied graph) instead of waiting."""
    client = FakeClient(
        {"Endpoint": ["paysim-acct-1", "paysim-acct-2"], "TRANSACTED": ["paysim-tx-1"]}
    )
    client.record_missing_on = "DELETE"
    client.truncate_times_out = True
    client.empties_after_polls = 2
    assert _clear(client) == (2, 1)
    assert client.rows == {"Endpoint": [], "TRANSACTED": []}


def test_a_truncate_that_never_finishes_is_an_error_naming_the_type() -> None:
    """Catches waiting forever, and reporting success while rows remain."""
    client = FakeClient({"Endpoint": ["paysim-acct-1"], "TRANSACTED": ["paysim-tx-1"]})
    client.record_missing_on = "DELETE"
    client.truncate_times_out = True
    client.empties_after_polls = 10**6
    with pytest.raises(
        seed_support.CleanUpIncomplete, match="TRANSACTED.*still not empty"
    ):
        _clear(client, wait_seconds=30.0)


def test_the_clean_up_says_what_it_is_doing() -> None:
    """Seen: the clean-up printed nothing and looked hung."""
    said: list[str] = []
    client = FakeClient({"Endpoint": ["paysim-acct-1"], "TRANSACTED": ["paysim-tx-1"]})
    asyncio.run(
        seed_support.clear_seeded_graph(
            client,  # type: ignore[arg-type]
            node_type="Endpoint",
            node_prefix="paysim-acct-",
            edge_type="TRANSACTED",
            edge_prefix="paysim-tx-",
            say=said.append,
            sleep=_no_sleep,
        )
    )
    assert said and "1 accounts and 1 transactions to remove" in said[0]


class _Server:
    """A stand-in ArcadeDB server that knows which databases exist."""

    def __init__(self, databases: list[str], *, drop_times_out: bool = False) -> None:
        self.databases = list(databases)
        self.drop_times_out = drop_times_out
        self.calls: list[str] = []
        self.lists_until_gone = 0

    async def drop_database(self) -> None:
        self.calls.append("drop")
        if self.drop_times_out:
            self.lists_until_gone = 2
            raise httpx.ReadTimeout("read timed out")
        self.databases = [d for d in self.databases if d != "ospreyflow"]

    async def create_database_if_absent(self) -> None:
        self.calls.append("create")
        if "ospreyflow" not in self.databases:
            self.databases.append("ospreyflow")

    async def list_databases(self) -> list[str]:
        if self.drop_times_out and self.lists_until_gone > 0:
            self.lists_until_gone -= 1
            if self.lists_until_gone == 0:
                self.databases = [d for d in self.databases if d != "ospreyflow"]
        return list(self.databases)


def _reset(server: _Server, *, wait_seconds: float = 600.0) -> list[str]:
    said: list[str] = []
    asyncio.run(
        seed_support.reset_graph_database(
            server,
            database="ospreyflow",
            say=said.append,
            sleep=_no_sleep,
            wait_seconds=wait_seconds,
        )
    )
    return said


def test_the_reset_drops_then_recreates_only_the_named_database() -> None:
    """Catches a reset that drops another database on the server, or forgets to recreate."""
    server = _Server(["ospreyflow", "other"])
    said = _reset(server)
    assert server.calls == ["drop", "create"]
    assert server.databases == ["other", "ospreyflow"]
    assert "all graph data" in said[0]


def test_a_drop_the_client_gives_up_on_is_waited_for() -> None:
    """The same 30-second client limit as the truncate: the server carries on."""
    server = _Server(["ospreyflow"], drop_times_out=True)
    _reset(server)
    assert server.calls == ["drop", "create"] and "ospreyflow" in server.databases


def test_a_database_that_will_not_go_is_an_error_not_a_success() -> None:
    server = _Server(["ospreyflow"], drop_times_out=True)
    server.lists_until_gone = 10**6

    async def stuck_drop() -> None:
        server.calls.append("drop")
        raise httpx.ReadTimeout("read timed out")

    server.drop_database = stuck_drop  # type: ignore[method-assign]
    with pytest.raises(seed_support.CleanUpIncomplete, match="still exists"):
        _reset(server, wait_seconds=10.0)
    assert "create" not in server.calls


def test_a_vault_gets_its_own_database_and_its_own_analytics_file() -> None:
    """Catches two vaults sharing a file, and a hyphen that ArcadeDB would refuse."""
    found = seed_support.vault_locations(
        "fixture-corp", "/data/_local-runtime/analytics.duckdb"
    )
    assert found.database == "vault_fixture_corp"
    assert (
        found.analytics_db_path
        == "/data/_local-runtime/vaults/fixture-corp/analytics.duckdb"
    )
    other = seed_support.vault_locations(
        "paysim", "/data/_local-runtime/analytics.duckdb"
    )
    assert (
        other.database != found.database
        and other.analytics_db_path != found.analytics_db_path
    )


@pytest.mark.parametrize(
    "bad", ["", "PaySim", "../x", "a/b", "1abc", "a" * 32, "x y", "a_b"]
)
def test_a_vault_id_that_could_escape_its_folder_is_refused(bad: str) -> None:
    """Catches an id that builds a path outside `vaults/`."""
    with pytest.raises(ValueError, match="not a vault id"):
        seed_support.vault_locations(bad, "/data/analytics.duckdb")


def test_the_events_summary_reports_each_case_and_each_way_a_file_can_be_unreadable(
    tmp_path: Path,
) -> None:
    """Catches a verification that says nothing when the file is missing or locked, and one that
    could write."""
    missing = tmp_path / "none.duckdb"
    assert "does not exist" in seed_support.events_summary(missing)[0]

    path = tmp_path / "a.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE other (x INTEGER)")
    con.close()
    assert "no events table" in seed_support.events_summary(path)[0]

    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE events (investigation_scope VARCHAR)")
    con.close()
    assert "empty" in seed_support.events_summary(path)[0]

    con = duckdb.connect(str(path))
    con.execute("INSERT INTO events VALUES ('c1'), ('c1'), ('c2')")
    con.close()
    lines = seed_support.events_summary(path)
    assert any("2 events in case c1" in x for x in lines)
    assert any("1 events in case c2" in x for x in lines)
    con = duckdb.connect(str(path), read_only=True)
    assert con.execute("SELECT count(*) FROM events").fetchone() == (3,)
    con.close()


def test_a_file_someone_else_has_open_is_reported_not_crashed_on(
    tmp_path: Path,
) -> None:
    path = tmp_path / "busy.duckdb"
    holder = duckdb.connect(str(path))
    holder.execute("CREATE TABLE events (investigation_scope VARCHAR)")
    try:
        assert "cannot be opened now" in seed_support.events_summary(path)[0]
    finally:
        holder.close()


# --- reading what the graph holds, without changing it (ADR-055 Amendment 6) ---


class ProbeClient:
    def __init__(
        self, fail_on: str | None = None, duplicate_id: str | None = None
    ) -> None:
        self.statements: list[str] = []
        self.fail_on = fail_on
        self.duplicate_id = duplicate_id

    async def sql(self, command: str, **_: object) -> list[dict[str, object]]:
        from adapters.graph_arcadedb.client import ArcadeDBError

        self.statements.append(command)
        if self.fail_on and self.fail_on in command:
            raise ArcadeDBError(
                "ArcadeDB error 404: Record #169:80 not found",
                status_code=404,
                exception_class="com.arcadedb.exception.RecordNotFoundException",
            )
        if self.duplicate_id and "GROUP BY id" in command and "TRANSACTED" in command:
            return [
                {"id": self.duplicate_id, "n": 2},
                {"id": "paysim-tx-second", "n": 2},
            ]
        if command.startswith("SELECT FROM TRANSACTED WHERE id LIKE"):
            return [
                {"id": self.duplicate_id, "source": "acct-a", "target": "acct-b"}
            ] * 2
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


def test_inspect_looks_for_duplicate_ids_and_totals_the_occurrences() -> None:
    """Seen: a vault held 13,076 transactions after 13,068 were written. Catches an inspection
    that cannot tell a duplicated id from a genuinely larger graph."""
    client = ProbeClient()
    _inspect(client)
    assert any("GROUP BY id" in s and "TRANSACTED" in s for s in client.statements)
    assert any("GROUP BY id" in s and "Endpoint" in s for s in client.statements)
    assert any("sum(occurrences)" in s for s in client.statements)
    assert all(s.startswith("SELECT") for s in client.statements)


def test_inspect_counts_the_ids_stored_more_than_once() -> None:
    """Seen twice: the five most-stored ids were each stored twice, which says duplicates exist but
    not how many. Counted from the grouped rows, because ArcadeDB's parser refuses the subquery
    form (`SELECT count(*) FROM (SELECT ...)`, seen 30 September 2026)."""
    client = ProbeClient(duplicate_id="paysim-tx-abc")
    lines = _inspect(client)
    assert not any("FROM (SELECT" in s for s in client.statements)
    assert any("stored more than once: 2" in line for line in lines)
    assert any("stored more than once: 0" in line for line in _inspect(ProbeClient()))


def test_inspect_shows_both_records_of_a_duplicated_id_by_a_scan_not_the_index() -> (
    None
):
    """Seen: the group count said an id was stored twice, but `WHERE id = '...'` returned one
    record: the lookup used an index that hid the second. `LIKE` is not answered from that index,
    so both records show."""
    client = ProbeClient(duplicate_id="paysim-tx-abc")
    lines = _inspect(client)
    follow = [
        s for s in client.statements if s.startswith("SELECT FROM TRANSACTED WHERE id")
    ]
    assert follow == ["SELECT FROM TRANSACTED WHERE id LIKE 'paysim-tx-abc'"]
    assert any("paysim-tx-abc" in line and "both records" in line for line in lines)


def test_inspect_does_not_look_up_records_when_nothing_is_duplicated() -> None:
    client = ProbeClient()
    _inspect(client)
    assert not any(
        s.startswith("SELECT FROM TRANSACTED WHERE id") for s in client.statements
    )


def test_inspect_escapes_a_quote_in_a_duplicated_id() -> None:
    """The id comes from the database; a quote in it must not break out of the literal."""
    client = ProbeClient(duplicate_id="paysim-tx-a'b")
    _inspect(client)
    assert any("LIKE 'paysim-tx-a\\'b'" in s for s in client.statements)


def test_inspect_looks_for_a_second_vertex_behind_each_end_of_a_duplicate_by_a_scan() -> (
    None
):
    """Seen: the two records of a duplicated id were identical down to the microsecond, so one
    write made two edges. If an endpoint vertex is reachable twice, one traversal fans out to two
    edges; `LIKE` is answered by a scan, which shows a second vertex an index would hide."""
    client = ProbeClient(duplicate_id="paysim-tx-abc")
    _inspect(client)
    for end in ("acct-a", "acct-b"):
        assert (
            f"SELECT @rid AS rid, id FROM Endpoint WHERE id LIKE '{end}'"
            in client.statements
        )


def test_inspect_lists_every_duplicated_id_compactly_not_only_the_first() -> None:
    """Seen: 8 ids were duplicated; whether they share an account or a position is the clue."""
    client = ProbeClient(duplicate_id="paysim-tx-abc")
    _inspect(client)
    assert (
        "SELECT @rid AS rid, source, target FROM TRANSACTED WHERE id LIKE 'paysim-tx-second'"
        in client.statements
    )


def test_event_progress_says_how_many_how_long_and_how_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seen: the event load of a seed printed '50,000 events loaded' and nothing else, so its pace
    could not be read. Catches a line without the elapsed time, or a speed worked out over the
    whole run (or the wrong count) in place of the last batch."""
    clock = iter([0.0, 10.0, 70.0, 70.0])
    monkeypatch.setattr(seed_support.time, "monotonic", lambda: next(clock))
    lines: list[str] = []
    progress = seed_support.EventProgress(lines.append)  # reads the clock once, at 0.0
    progress(50_000)  # at 10.0
    progress(100_000)  # at 70.0: 50,000 more in 60 s
    assert lines == [
        "  50,000 events loaded (0m 10s, 5,000 per s)",
        "  100,000 events loaded (1m 10s, 833 per s)",
    ]
