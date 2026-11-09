"""Phase 9's SQL connector against a real PostgreSQL, live under a lease (`06_DECISIONS.md` ADR-140
Amendment 13; the redesign's phase 9; rule 14). **The phase's exit:** `visit_bookings`, a synthetic
NOMIS-replica table (rule 9: invented rows) in the leased stack's Postgres, is registered with an
incremental watermark, and a refresh reads only the new rows.

The leased Postgres is the fixture, and it refuses what a real one refuses (rule 15): a wrong
password, a table that is not there, a write through a read-only transaction. It differs from a
deployment in two named ways, each taken by `_no_tls` alone: it is on this machine, which every
connection refuses (`test_connector_hosts.py`), so its settings name `FIXTURE_HOST` and the hook
connects to the leased port instead; and it lacks TLS, so the hook asks for none.
`test_a_server_without_tls_is_refused` connects through `_to_the_stack`, which takes the address and
keeps TLS, to prove the real connector refuses that same server. The `verify-full` cases at the end
put a TLS front before it instead, so the connector's own TLS is used unchanged.

**The exit, end to end.**
`test_the_exit_visit_bookings_is_registered_and_refreshed_through_the_routes` registers
`visit_bookings` through `POST /v1/datasets/{id}/sources` and refreshes it through *Refresh now*,
over the Postgres source store and its cursor.
`test_a_sql_sources_refreshed_file_loads_only_new_rows` loads the connector's file through the path
a source refresh takes (`run_published_recipe` with the source's watermark, a real run ledger,
ArcadeDB). It reads a payments-shaped synthetic table, because that path's only published live
recipe is the refresh tests' payments recipe; the read and the file are the connector's own.

What a mistake would do, and the case that catches it:
- a login that can write accepted as read-only — `test_a_login_that_can_write_is_refused`;
- an incremental refresh reading every row again, or skipping one —
  `test_visit_bookings_is_read_incrementally_and_a_refresh_reads_only_new_rows` (the exit);
- a refused sign-in or a missing table read as no rows — `test_refusals_are_refused_in_words`;
- a server without TLS accepted — `test_a_server_without_tls_is_refused`;
- the byte cap counted in characters, or checked only after a row past it is held —
  `test_the_byte_cap_counts_bytes_not_characters`, `test_a_row_past_the_byte_cap_is_never_held`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.ingest.connectors.reads import ConnectorRefused, write_snapshot
from services.ingest.connectors.sql_connector import check_sql_connection, read_sql
from services.ingest.watermark import read_past

from schemas.sources import SqlConnectionSettings, SqlRead
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the fixture, by name)
from tests.services.api.test_source_refresh_snapshot_live import runs  # noqa: F401 (by name)

READER, WRITER, PASSWORD = "osprey_fixture_reader", "osprey_fixture_writer", "fixture-only-pw"
BOOKINGS = [
    (1, "SYN-P-0001", "HMP Synthetic One", "2026-11-01T09:00:00+00:00"),
    (2, "SYN-P-0002", "HMP Synthetic One", "2026-11-01T10:30:00+00:00"),
    (3, "SYN-P-0003", "HMP Synthetic Two", "2026-11-02T14:00:00+00:00"),
]
LATER = [
    (4, "SYN-P-0004", "HMP Synthetic Two", "2026-11-03T09:15:00+00:00"),
    (5, "SYN-P-0001", "HMP Synthetic One", "2026-11-04T11:00:00+00:00"),
]


#: The fixture's host as its settings name it: a name every check admits, which only the hooks below
#: take to the leased stack's Postgres on this machine.
FIXTURE_HOST = "nomis-replica.fixture.example"


async def _to_the_stack(**kw: Any) -> Any:
    """The leased Postgres is on this machine, which no connection may name: connect there."""
    assert kw["host"] == FIXTURE_HOST
    return await asyncpg.connect(**{**kw, "host": "localhost"})


async def _no_tls(**kw: Any) -> Any:
    """The fixture's two differences: on this machine, and with no TLS to ask for."""
    return await _to_the_stack(**{**kw, "ssl": False})


def _admit_the_fixture(kind: str, host: str, allowed: object) -> None:
    """The route's host check for the fixture alone: it admits `FIXTURE_HOST` and nothing else."""
    assert host == FIXTURE_HOST, host


def _settings(user: str = READER) -> SqlConnectionSettings:
    return SqlConnectionSettings(
        host=FIXTURE_HOST,
        schemas=["nomis_replica_fixture"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=PostgresConfig.from_env().dsn.rsplit("/", 1)[-1],
        user=user,
        secret="NOMIS_FIXTURE",
    )


@pytest.fixture
async def nomis() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await _setup(conn)
        yield conn
    finally:
        # The schema's drop takes the roles' grants with it, so the roles drop whether or not the
        # setup got as far as making them (the lane review of L1.6, item 18).
        try:
            await conn.execute(f"""
                DROP SCHEMA IF EXISTS nomis_replica_fixture CASCADE;
                DROP ROLE IF EXISTS {READER}; DROP ROLE IF EXISTS {WRITER};
            """)
        finally:
            await conn.close()


async def _setup(conn: asyncpg.Connection) -> None:
    await conn.execute(f"""
        DROP SCHEMA IF EXISTS nomis_replica_fixture CASCADE;
        DROP ROLE IF EXISTS {READER}; DROP ROLE IF EXISTS {WRITER};
        CREATE SCHEMA nomis_replica_fixture;
        CREATE TABLE nomis_replica_fixture.visit_bookings (
            booking_id integer PRIMARY KEY, prisoner text NOT NULL, establishment text NOT NULL,
            booked_for timestamptz NOT NULL);
        CREATE ROLE {READER} LOGIN PASSWORD '{PASSWORD}';
        CREATE ROLE {WRITER} LOGIN PASSWORD '{PASSWORD}';
        GRANT USAGE ON SCHEMA nomis_replica_fixture TO {READER}, {WRITER};
        GRANT SELECT ON nomis_replica_fixture.visit_bookings TO {READER};
        GRANT SELECT, INSERT ON nomis_replica_fixture.visit_bookings TO {WRITER};
    """)
    await _insert(conn, BOOKINGS)


async def _insert(conn: asyncpg.Connection, rows: list[tuple[Any, ...]]) -> None:
    await conn.executemany(
        "INSERT INTO nomis_replica_fixture.visit_bookings VALUES ($1, $2, $3, $4)",
        [(*r[:3], datetime.fromisoformat(r[3])) for r in rows],
    )


READ = SqlRead(table="nomis_replica_fixture.visit_bookings")


async def test_a_login_that_can_write_is_refused(nomis: asyncpg.Connection) -> None:
    reader = await check_sql_connection(_settings(), secret=PASSWORD, connect=_no_tls)
    assert reader.ok, reader.words
    writer = await check_sql_connection(_settings(WRITER), secret=PASSWORD, connect=_no_tls)
    assert not writer.ok and "read-only login only" in writer.words
    with pytest.raises(ConnectorRefused, match="read-only login only"):
        await read_sql(_settings(WRITER), READ, secret=PASSWORD, connect=_no_tls)


async def test_visit_bookings_is_read_incrementally_and_a_refresh_reads_only_new_rows(
    nomis: asyncpg.Connection, tmp_path: Path
) -> None:
    first = await read_sql(
        _settings(), READ, secret=PASSWORD, watermark="booking_id", connect=_no_tls
    )
    assert [r["booking_id"] for r in first.rows] == ["1", "2", "3"] and first.cursor == "3"
    assert first.columns == ["booking_id", "prisoner", "establishment", "booked_for"]
    folder = tmp_path / "uploaded" / "nomis"
    file_1 = write_snapshot(first, folder, "visit_bookings").read_text()
    await _insert(nomis, LATER)
    second = await read_sql(
        _settings(),
        READ,
        secret=PASSWORD,
        watermark="booking_id",
        cursor=first.cursor,
        connect=_no_tls,
    )
    assert [r["booking_id"] for r in second.rows] == ["4", "5"] and second.cursor == "5"
    file_2 = write_snapshot(second, folder, "visit_bookings").read_text()
    assert "SYN-P-0003" in file_1 and "SYN-P-0003" not in file_2
    nothing = await read_sql(
        _settings(),
        READ,
        secret=PASSWORD,
        watermark="booking_id",
        cursor=second.cursor,
        connect=_no_tls,
    )
    assert nothing.rows == [] and nothing.cursor == "5"
    # And the run's own watermark, kept at 3 after the first load, reads the second file whole
    # and the first file's rows not at all: a refresh loads only new rows, by either guard.
    kept = read_past(first.rows, source_id="src", column="booking_id", kept=None)  # type: ignore[arg-type]
    again = read_past(
        first.rows + second.rows,
        source_id="src",
        column="booking_id",  # type: ignore[arg-type]
        kept=kept.reached,
    )
    assert [r["booking_id"] for r in again.rows] == ["4", "5"] and again.below == 3


async def test_a_watermark_on_a_time_reads_past_its_value(nomis: asyncpg.Connection) -> None:
    got = await read_sql(
        _settings(),
        READ,
        secret=PASSWORD,
        watermark="booked_for",
        cursor="2026-11-01T10:30:00+00:00",
        connect=_no_tls,
    )
    assert [r["booking_id"] for r in got.rows] == ["3"]


# --- The byte cap (the independent review of L1.6, carried into L1.8) ---------------------------
# A read is capped at `reads.MAX_BYTES`, counted in bytes (UTF-8), not characters, and checked before
# a row is held: the server keeps the running count, so a row past the cap is never sent, and the
# row that crosses it is sent without its values. Shown red at main
# (`process/lanes/studio-b/l1.8/red-carry-byte-cap.txt`).

NOTES = SqlRead(table="nomis_replica_fixture.case_notes")


async def _notes(conn: asyncpg.Connection, notes: list[str]) -> None:
    """A synthetic notes table the fixture's reader may read; dropped with the fixture's schema."""
    await conn.execute(f"""
        CREATE TABLE nomis_replica_fixture.case_notes (note_id integer PRIMARY KEY, note text NOT NULL);
        GRANT SELECT ON nomis_replica_fixture.case_notes TO {READER};
    """)
    await conn.executemany(
        "INSERT INTO nomis_replica_fixture.case_notes VALUES ($1, $2)", list(enumerate(notes, 1))
    )


class _Counted:
    """The connection a read is given, counting the bytes of every value its cursors hand over: what
    the read came to hold. Everything else passes through."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self.received = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def cursor(self, *args: Any, **kwargs: Any) -> Any:
        rows = self._conn.cursor(*args, **kwargs)
        counted = self

        class _Rows:
            def __aiter__(self) -> Any:
                self._inner = rows.__aiter__()
                return self

            async def __anext__(self) -> Any:
                record = await self._inner.__anext__()
                counted.received += sum(
                    len(str(v).encode("utf-8")) for v in record.values() if v is not None
                )
                return record

        return _Rows()


async def test_the_byte_cap_counts_bytes_not_characters(
    nomis: asyncpg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """600 characters of `é` are 1,200 bytes: over a 1,000-byte cap, though under it in characters."""
    from services.ingest.connectors import reads

    await _notes(nomis, ["é" * 600])
    monkeypatch.setattr(reads, "MAX_BYTES", 1000)
    with pytest.raises(ConnectorRefused, match="more than 1000 bytes"):
        await read_sql(_settings(), NOTES, secret=PASSWORD, connect=_no_tls)
    monkeypatch.setattr(reads, "MAX_BYTES", 1300)
    got = await read_sql(_settings(), NOTES, secret=PASSWORD, connect=_no_tls)
    assert [r["note"] for r in got.rows] == ["é" * 600]


@pytest.mark.parametrize("watermark", [None, "note_id"], ids=["whole", "incremental"])
async def test_a_row_past_the_byte_cap_is_never_held(
    nomis: asyncpg.Connection, monkeypatch: pytest.MonkeyPatch, watermark: str | None
) -> None:
    """Three short notes, then three of 100 KB, under a 1,000-byte cap: refused, and the read never
    holds more than the cap, however the rows after the cap are sized."""
    from services.ingest.connectors import reads

    await _notes(nomis, ["short note"] * 3 + ["x" * 100_000] * 3)
    monkeypatch.setattr(reads, "MAX_BYTES", 1000)
    held: list[_Counted] = []

    async def counted(**kw: Any) -> Any:
        held.append(_Counted(await _no_tls(**kw)))
        return held[-1]

    with pytest.raises(ConnectorRefused, match="more than 1000 bytes"):
        await read_sql(_settings(), NOTES, secret=PASSWORD, watermark=watermark, connect=counted)
    assert held and held[0].received <= 1000, held[0].received
    monkeypatch.setattr(reads, "MAX_BYTES", 400_000)
    got = await read_sql(_settings(), NOTES, secret=PASSWORD, watermark=watermark, connect=_no_tls)
    assert [r["note_id"] for r in got.rows] == ["1", "2", "3", "4", "5", "6"]
    assert got.columns == ["note_id", "note"]


async def test_refusals_are_refused_in_words(nomis: asyncpg.Connection) -> None:
    with pytest.raises(ConnectorRefused, match="refused the sign-in"):
        await read_sql(_settings(), READ, secret="wrong", connect=_no_tls)
    with pytest.raises(ConnectorRefused, match="refused the read"):
        await read_sql(
            _settings(),
            SqlRead(table="nomis_replica_fixture.no_such"),
            secret=PASSWORD,
            connect=_no_tls,
        )
    with pytest.raises(ConnectorRefused, match="no column"):
        await read_sql(_settings(), READ, secret=PASSWORD, watermark="no_such", connect=_no_tls)
    with pytest.raises(ConnectorRefused, match="secret is not set"):
        await read_sql(_settings(), READ, secret=None, connect=_no_tls)


async def test_a_server_without_tls_is_refused(nomis: asyncpg.Connection) -> None:
    with pytest.raises(ConnectorRefused, match="TLS"):
        await read_sql(_settings(), READ, secret=PASSWORD, connect=_to_the_stack)
    tested = await check_sql_connection(_settings(), secret=PASSWORD, connect=_to_the_stack)
    assert not tested.ok and "TLS" in tested.words


# --- the exit through the routes, and the load (the lane review of L1.6, item 2) -----------------

import csv as _csv  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import httpx  # noqa: E402
from services.api.app import app  # noqa: E402
from services.api.connector_reads import Readers  # noqa: E402
from services.api.datasets import Dataset, InMemoryDatasetStore  # noqa: E402
from services.api.sources import PostgresSourceStore  # noqa: E402

from schemas.domain import Principal  # noqa: E402

PEOPLE = {
    "engineer": Principal(
        id="eng-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]
    ),
    "admin": Principal(id="adm-1", clearance="SECRET", org_unit="unit-1", roles=["osprey-admin"]),
}
HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Cases:
    async def list_for(self, principal: Principal) -> list[tuple[object, str]]:
        return [(SimpleNamespace(id="case-exit"), "editor")] if principal.id == "eng-1" else []


class _Recipes:
    async def using_source(self, dataset_id: str, location: str) -> list[object]:
        return []


class _Audit:
    async def record(self, **kwargs: object) -> None:
        return None


def _rows_of(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(_csv.DictReader(handle))


async def test_the_exit_visit_bookings_is_registered_and_refreshed_through_the_routes(
    nomis: asyncpg.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "ingest"
    (root / "uploaded" / "ds-exit").mkdir(parents=True)
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    monkeypatch.setenv("OSPREY_CONNECTION_SECRET_NOMIS_FIXTURE", PASSWORD)
    monkeypatch.setenv("OSPREY_CONNECTOR_SECRETS", "NOMIS_FIXTURE")  # declared (Amendment 15)
    from services.api import connector_reads

    monkeypatch.setattr(connector_reads, "resolve_host", lambda host: [])  # no lookup leaves
    datasets = InMemoryDatasetStore()
    datasets.add(
        Dataset(
            id="ds-exit",
            name="NOMIS replica (synthetic)",
            owning_unit="unit-1",
            created_by="s",
            created_at=datetime(2026, 1, 1),
        )
    )
    datasets.cases["case-exit"] = ["ds-exit"]
    sources = await PostgresSourceStore.connect(PostgresConfig.from_env().dsn)
    state = {
        "principal_resolver": _Resolver(),
        "investigations": _Cases(),
        "datasets": datasets,
        "sources": sources,
        "studio_recipes": _Recipes(),
        "audit": _Audit(),
        "connector_readers": Readers(sql_connect=_no_tls, host_check=_admit_the_fixture),
    }
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    settings = _settings().model_dump()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://conduit"
        ) as client:
            made = await client.post(
                "/v1/admin/connections",
                headers={"Authorization": "Bearer admin"},
                json={
                    "kind": "sql",
                    "name": "NOMIS replica",
                    "settings": settings,
                    "datasets": ["ds-exit"],
                },
            )
            assert made.status_code == 201, made.text
            body = {
                "connection_id": made.json()["id"],
                "name": "Visit bookings",
                "location": "visit_bookings",
                "handling": HANDLING,
                "read": {"kind": "sql", "table": "nomis_replica_fixture.visit_bookings"},
                "refresh": {
                    "trigger": "watch",
                    "pattern": "x",
                    "mode": "incremental",
                    "watermark_column": "booking_id",
                },
            }
            registered = await client.post(
                "/v1/datasets/ds-exit/sources",
                json=body,
                headers={"Authorization": "Bearer engineer"},
            )
            assert registered.status_code == 201, registered.text
            source = registered.json()
            file = root / "uploaded" / "ds-exit" / "visit_bookings.csv"
            assert source["location"] == str(file)
            assert source["refresh"]["pattern"] == "visit_bookings.csv"
            assert [r["booking_id"] for r in _rows_of(file)] == ["1", "2", "3"]
            assert await sources.cursor(source["id"]) == "3"
            first_loaded = _rows_of(file)

            await _insert(nomis, LATER)
            refreshed = await client.post(
                f"/v1/datasets/ds-exit/sources/{source['id']}/read",
                headers={"Authorization": "Bearer engineer"},
            )
            assert refreshed.status_code == 200 and refreshed.json()["rows"] == 2, refreshed.text
            assert await sources.cursor(source["id"]) == "5"
            held = _rows_of(file)
            assert [r["booking_id"] for r in held] == ["1", "2", "3", "4", "5"]
            again = await client.post(
                f"/v1/datasets/ds-exit/sources/{source['id']}/read",
                headers={"Authorization": "Bearer engineer"},
            )
            assert again.json()["rows"] == 0 and "left as it was" in again.json()["words"]
            assert _rows_of(file) == held
        kept = read_past(first_loaded, source_id=source["id"], column="booking_id", kept=None)
        refresh = read_past(held, source_id=source["id"], column="booking_id", kept=kept.reached)
        assert [r["booking_id"] for r in refresh.rows] == ["4", "5"]
    finally:
        conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
        await conn.execute("DELETE FROM ingest_sources WHERE dataset_id = 'ds-exit'")
        await conn.execute("DELETE FROM ingest_connections WHERE name = 'NOMIS replica'")
        await conn.close()
        await sources.close()


async def test_a_sql_sources_refreshed_file_loads_only_new_rows(
    nomis: asyncpg.Connection,
    tmp_path: Path,
    runs: object,  # noqa: F811 (the fixture)
) -> None:
    from adapters.analytics_duckdb.testing import duckdb_adapter
    from adapters.graph_arcadedb.testing import arcadedb_adapter
    from tests.ingest.test_row_keys import ONTOLOGY, SCHEME
    from tests.services.api.test_source_refresh_incremental_live import READ as PAID_AT
    from tests.services.api.test_source_refresh_snapshot_live import Refresh

    await nomis.execute(f"""
        CREATE TABLE nomis_replica_fixture.payments (
            payer text NOT NULL, payee text NOT NULL, paid_at timestamptz NOT NULL, memo text);
        GRANT SELECT ON nomis_replica_fixture.payments TO {READER};
    """)
    pay = "INSERT INTO nomis_replica_fixture.payments VALUES ($1, $2, $3, NULL)"
    for payer, payee, day in (("SYN-1", "SYN-2", 1), ("SYN-3", "SYN-4", 2)):
        await nomis.execute(
            pay, payer, payee, datetime.fromisoformat(f"2026-03-0{day}T09:00:00+00:00")
        )
    read = SqlRead(
        table="nomis_replica_fixture.payments", columns=["payer", "payee", "paid_at", "memo"]
    )
    folder = tmp_path / "uploaded" / "ds-pay"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph, duckdb_adapter([], SCHEME) as analytics:
        refresh = Refresh(tmp_path, runs, graph, analytics)  # type: ignore[arg-type]
        got = await read_sql(
            _settings(), read, secret=PASSWORD, watermark="paid_at", connect=_no_tls
        )
        file = write_snapshot(got, folder, "payments", keep_earlier=True)
        first = await refresh.snapshot(_rows_of(file), PAID_AT)
        assert first.nodes_created == 4  # type: ignore[attr-defined]

        await nomis.execute(
            pay, "SYN-5", "SYN-6", datetime.fromisoformat("2026-03-03T09:00:00+00:00")
        )
        more = await read_sql(
            _settings(),
            read,
            secret=PASSWORD,
            watermark="paid_at",
            cursor=got.cursor,
            connect=_no_tls,
        )
        assert len(more.rows) == 1
        file = write_snapshot(more, folder, "payments", keep_earlier=True)
        second = await refresh.snapshot(_rows_of(file), PAID_AT)
        assert second.rows_read == 1 and second.rows_below_watermark == 2  # type: ignore[attr-defined]
        assert second.nodes_created == 2  # type: ignore[attr-defined]
        assert await refresh.values() == {"SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5", "SYN-6"}


async def test_a_write_in_the_connectors_session_is_refused_by_the_server(
    nomis: asyncpg.Connection,
) -> None:
    """The orchestrator's second review (item 7): even a login that may write (refused before any
    read by `read_sql`) cannot write in a session the connector opens, since the server holds it
    read-only from its first statement."""
    from services.ingest.connectors.sql_connector import _open

    conn = await _open(_settings(WRITER), PASSWORD, _no_tls)
    try:
        with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
            await conn.execute(
                "INSERT INTO nomis_replica_fixture.visit_bookings VALUES "
                "(99, 'SYN-P-0099', 'HMP Synthetic Two', now())"
            )
        assert await conn.fetchval("SHOW statement_timeout") == "1min"
    finally:
        await conn.close()
    count = await nomis.fetchval("SELECT count(*) FROM nomis_replica_fixture.visit_bookings")
    assert count == len(BOOKINGS)


# --- verify-full against a real TLS server (the orchestrator's second review, item 7) ----------
#
# A TLS front stands before the leased Postgres: it answers Postgres's SSLRequest, finishes TLS with
# a certificate a synthetic CA (made here) signed for one name, and relays the decrypted bytes to
# the leased Postgres over plain TCP. The server's own settings and files are never touched, so
# there is nothing on the shared stack to put back (the lane review of Amendment 15, items 6 and 7).
# The connector is used exactly as a deployment uses it: its own `verify-full` context, the
# connection's own CA certificate (ADR-140 Amendment 15 decision 6), and the checked address with
# the host's name kept for the name check. What a mistake would do:
# - `verify-full` that verifies nothing (no CERT_REQUIRED, or no name check) — the untrusted-CA and
#   other-name cases read rows, and the front relays the sign-in to Postgres;
# - the connection's CA not trusted, or the name checked against the address it connected to —
#   `test_verify_full_reads_over_tls_from_a_server_it_trusts` is refused.

import asyncio  # noqa: E402
import ssl as _ssl  # noqa: E402
import struct  # noqa: E402

from tests.connectors.tls_fixture import Ca, make_ca  # noqa: E402

TLS_NAME = "nomis-tls.fixture.example"
_SSL_REQUEST = struct.pack("!ii", 8, 80877103)


class _TlsFront:
    """TLS before the leased Postgres, for one certificate; counts what it relayed."""

    def __init__(self, cert_pem: bytes, key_pem: bytes, tmp: Path) -> None:
        (tmp / "front.crt").write_bytes(cert_pem)
        (tmp / "front.key").write_bytes(key_pem)
        self.context = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(tmp / "front.crt", tmp / "front.key")
        self.handshakes = 0
        self.relayed = 0  # bytes of the client's, decrypted and passed on to Postgres
        self.port = 0
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            if await reader.readexactly(8) != _SSL_REQUEST:
                return
            writer.write(b"S")
            await writer.drain()
            await writer.start_tls(self.context)
        except (OSError, _ssl.SSLError, asyncio.IncompleteReadError):
            writer.close()
            return
        self.handshakes += 1
        up_reader, up_writer = await asyncio.open_connection(
            "127.0.0.1", int(os.environ["POSTGRES_PORT"])
        )

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter, count: bool) -> None:
            try:
                while data := await src.read(65536):
                    if count:
                        self.relayed += len(data)
                    dst.write(data)
                    await dst.drain()
            except (OSError, _ssl.SSLError):
                pass
            finally:
                dst.close()

        await asyncio.gather(pipe(reader, up_writer, True), pipe(up_reader, writer, False))


@pytest.fixture
def fixture_ca() -> Ca:
    return make_ca()


async def _front_for(name: str, ca: Ca, tmp: Path) -> _TlsFront:
    front = _TlsFront(*ca.server(name), tmp)
    await front.start()
    return front


def _tls_settings(port: int, ca_pem: str | None) -> SqlConnectionSettings:
    return _settings().model_copy(
        update={"host": TLS_NAME, "port": port, "tls": "verify-full", "ca_certificate": ca_pem}
    )


async def test_verify_full_reads_over_tls_from_a_server_it_trusts(
    nomis: asyncpg.Connection, fixture_ca: Ca, tmp_path: Path
) -> None:
    front = await _front_for(TLS_NAME, fixture_ca, tmp_path)
    try:
        settings = _tls_settings(front.port, fixture_ca.pem)
        tested = await check_sql_connection(settings, secret=PASSWORD, addresses=["127.0.0.1"])
        assert tested.ok, tested.words
        read = await read_sql(settings, READ, secret=PASSWORD, addresses=["127.0.0.1"])
        assert len(read.rows) == len(BOOKINGS)
        assert front.handshakes >= 2 and front.relayed > 0
    finally:
        await front.stop()


async def test_verify_full_refuses_a_certificate_from_a_ca_it_does_not_trust(
    nomis: asyncpg.Connection, fixture_ca: Ca, tmp_path: Path
) -> None:
    """The connection names no CA, so only the system's trust store is asked, which does not hold
    the fixture's CA: refused, and the sign-in never reaches Postgres."""
    front = await _front_for(TLS_NAME, fixture_ca, tmp_path)
    try:
        settings = _tls_settings(front.port, None)
        with pytest.raises(ConnectorRefused, match="certificate could not be verified"):
            await read_sql(settings, READ, secret=PASSWORD, addresses=["127.0.0.1"])
        tested = await check_sql_connection(settings, secret=PASSWORD, addresses=["127.0.0.1"])
        assert not tested.ok and "certificate could not be verified" in tested.words
        assert front.relayed == 0
    finally:
        await front.stop()


async def test_verify_full_refuses_a_certificate_for_another_name(
    nomis: asyncpg.Connection, fixture_ca: Ca, tmp_path: Path
) -> None:
    """A certificate the trusted CA signed, but for another name: refused by the name check."""
    front = await _front_for("other.fixture.example", fixture_ca, tmp_path)
    try:
        settings = _tls_settings(front.port, fixture_ca.pem)
        with pytest.raises(ConnectorRefused, match="certificate could not be verified"):
            await read_sql(settings, READ, secret=PASSWORD, addresses=["127.0.0.1"])
        assert front.relayed == 0
    finally:
        await front.stop()
