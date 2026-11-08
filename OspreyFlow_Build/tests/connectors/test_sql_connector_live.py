"""Phase 9's SQL connector against a real PostgreSQL, live under a lease (`06_DECISIONS.md` ADR-140
Amendment 13; the redesign's phase 9; rule 14). **The phase's exit:** `visit_bookings`, a synthetic
NOMIS-replica table (rule 9: invented rows) in the leased stack's Postgres, is registered with an
incremental watermark, and a refresh reads only the new rows.

The leased Postgres is the fixture, and it refuses what a real one refuses (rule 15): a wrong
password, a table that is not there, a write through a read-only transaction. It also lacks TLS, so
`test_a_server_without_tls_is_refused` proves the real connector refuses it. Every other case
connects through `_no_tls`, which drops TLS and nothing else. That is the fixture's one
difference from a deployment, and it is named here.

What a mistake would do, and the case that catches it:
- a login that can write accepted as read-only — `test_a_login_that_can_write_is_refused`;
- an incremental refresh reading every row again, or skipping one —
  `test_visit_bookings_is_read_incrementally_and_a_refresh_reads_only_new_rows` (the exit);
- a refused sign-in or a missing table read as no rows — `test_refusals_are_refused_in_words`;
- a server without TLS accepted — `test_a_server_without_tls_is_refused`.
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


async def _no_tls(**kw: Any) -> Any:
    """The fixture's one difference: the leased Postgres has no TLS, so it is asked for none."""
    return await asyncpg.connect(**{**kw, "ssl": False})


def _settings(user: str = READER) -> SqlConnectionSettings:
    return SqlConnectionSettings(host="localhost", port=int(os.environ["POSTGRES_PORT"]),
                                 database=PostgresConfig.from_env().dsn.rsplit("/", 1)[-1],
                                 user=user, secret="NOMIS_FIXTURE")  # fmt: skip


@pytest.fixture
async def nomis() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await _setup(conn)
        yield conn
    finally:
        await conn.execute(f"""
            DROP SCHEMA IF EXISTS nomis_replica_fixture CASCADE;
            DROP OWNED BY {READER}; DROP OWNED BY {WRITER};
            DROP ROLE IF EXISTS {READER}; DROP ROLE IF EXISTS {WRITER};
        """)  # fmt: skip
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
    """)  # fmt: skip
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
    first = await read_sql(_settings(), READ, secret=PASSWORD, watermark="booking_id",
                           connect=_no_tls)  # fmt: skip
    assert [r["booking_id"] for r in first.rows] == ["1", "2", "3"] and first.cursor == "3"
    assert first.columns == ["booking_id", "prisoner", "establishment", "booked_for"]
    folder = tmp_path / "uploaded" / "nomis"
    file_1 = write_snapshot(first, folder, "visit_bookings").read_text()
    await _insert(nomis, LATER)
    second = await read_sql(_settings(), READ, secret=PASSWORD, watermark="booking_id",
                            cursor=first.cursor, connect=_no_tls)  # fmt: skip
    assert [r["booking_id"] for r in second.rows] == ["4", "5"] and second.cursor == "5"
    file_2 = write_snapshot(second, folder, "visit_bookings").read_text()
    assert "SYN-P-0003" in file_1 and "SYN-P-0003" not in file_2
    nothing = await read_sql(_settings(), READ, secret=PASSWORD, watermark="booking_id",
                             cursor=second.cursor, connect=_no_tls)  # fmt: skip
    assert nothing.rows == [] and nothing.cursor == "5"
    # And the run's own watermark, kept at 3 after the first load, reads the second file whole
    # and the first file's rows not at all: a refresh loads only new rows, by either guard.
    kept = read_past(first.rows, source_id="src", column="booking_id", kept=None)  # type: ignore[arg-type]
    again = read_past(first.rows + second.rows, source_id="src", column="booking_id",  # type: ignore[arg-type]
                      kept=kept.reached)  # fmt: skip
    assert [r["booking_id"] for r in again.rows] == ["4", "5"] and again.below == 3


async def test_a_watermark_on_a_time_reads_past_its_value(nomis: asyncpg.Connection) -> None:
    got = await read_sql(_settings(), READ, secret=PASSWORD, watermark="booked_for",
                         cursor="2026-11-01T10:30:00+00:00", connect=_no_tls)  # fmt: skip
    assert [r["booking_id"] for r in got.rows] == ["3"]


async def test_refusals_are_refused_in_words(nomis: asyncpg.Connection) -> None:
    with pytest.raises(ConnectorRefused, match="refused the sign-in"):
        await read_sql(_settings(), READ, secret="wrong", connect=_no_tls)
    with pytest.raises(ConnectorRefused, match="refused the read"):
        await read_sql(_settings(), SqlRead(table="nomis_replica_fixture.no_such"),
                       secret=PASSWORD, connect=_no_tls)  # fmt: skip
    with pytest.raises(ConnectorRefused, match="no column"):
        await read_sql(_settings(), READ, secret=PASSWORD, watermark="no_such", connect=_no_tls)
    with pytest.raises(ConnectorRefused, match="secret is not set"):
        await read_sql(_settings(), READ, secret=None, connect=_no_tls)


async def test_a_server_without_tls_is_refused(nomis: asyncpg.Connection) -> None:
    with pytest.raises(ConnectorRefused, match="TLS"):
        await read_sql(_settings(), READ, secret=PASSWORD)
    tested = await check_sql_connection(_settings(), secret=PASSWORD)
    assert not tested.ok and "TLS" in tested.words
