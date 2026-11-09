"""Phase 9's SQL connector (`06_DECISIONS.md` ADR-140 Amendment 13; the redesign's phase 9): a table
of a PostgreSQL database read through a **read-only** login over TLS.

**Read-only, checked, twice.** *Test connection* and every read first ask the server whether the
login could change anything: a superuser, a table it owns, or a write privilege (`INSERT`, `UPDATE`,
`DELETE`, `TRUNCATE`) on any table it can see, its own grants and `PUBLIC`'s alike. Any of them
refuses the connection in words, before a row is read. The read itself then runs in a `READ ONLY`
transaction, so even a login wrongly granted a write could not use it here.

**TLS** is always asked for (`require`, or `verify-full` with the server's certificate and name
checked); a server that cannot speak it is refused.

**Names, never expressions** (rule 8): the table and its columns are identifiers the schema has
already checked, quoted here; the watermark's comparison takes its type from the server's own
catalogue, and its value is a bound parameter.

**Incremental.** With a watermark column, a read takes only rows past the highest value an earlier
read took (`cursor`), in order, and answers the new highest; the run's own watermark then applies as
built. A read past `reads.MAX_ROWS` rows is refused whole (rule 2).
"""

from __future__ import annotations

import re
import ssl
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg

from schemas.sources import ConnectionTest, SqlConnectionSettings, SqlRead

from . import reads
from .reads import ConnectorRefused, ReadRows, as_text

Connect = Callable[..., Awaitable[Any]]
#: How long one statement may run on the client's database, in milliseconds.
STATEMENT_TIMEOUT_MS = "60000"
#: A type the server's catalogue names: words, and a size in brackets.
_TYPE = re.compile(r"^[a-z][a-z0-9 _]*(\(\d+(,\s*\d+)?\))?(\[\])?$")

_WRITES = """
SELECT
  (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS superuser,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
      AND c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg_temp%') AS owned,
  (SELECT count(*) FROM pg_tables
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
      AND has_table_privilege(
        current_user, quote_ident(schemaname) || '.' || quote_ident(tablename),
        'INSERT, UPDATE, DELETE, TRUNCATE')) AS writable
"""


def _quoted(name: str) -> str:
    return ".".join(f'"{part}"' for part in name.split("."))


def _tls(settings: SqlConnectionSettings) -> ssl.SSLContext | str:
    if settings.tls == "verify-full":
        return ssl.create_default_context()
    return "require"


async def _open(settings: SqlConnectionSettings, secret: str | None, connect: Connect) -> Any:
    if not secret:
        raise ConnectorRefused("the connection's secret is not set; nothing was read")
    try:
        return await connect(
            host=settings.host, port=settings.port, user=settings.user, password=secret,
            database=settings.database, ssl=_tls(settings), timeout=15,
            # Every statement bounded, and the session read-only from its first statement (the
            # orchestrator's review of L1.6).
            server_settings={"statement_timeout": STATEMENT_TIMEOUT_MS,
                             "default_transaction_read_only": "on"},
        )  # fmt: skip
    except (OSError, asyncpg.PostgresError, ssl.SSLError, ConnectionError) as exc:
        words = str(exc).lower()
        if "ssl" in words or "tls" in words:
            raise ConnectorRefused(
                "the database would not speak TLS, which every SQL connection asks for; nothing "
                "was read"
            ) from exc
        if isinstance(
            exc, asyncpg.InvalidPasswordError | asyncpg.InvalidAuthorizationSpecificationError
        ):
            raise ConnectorRefused(
                "the database refused the sign-in: check the connection's login and secret; "
                "nothing was read"
            ) from exc
        raise ConnectorRefused(
            f"the database could not be reached ({type(exc).__name__}); nothing was read"
        ) from exc


async def _refuse_a_writing_login(conn: Any) -> None:
    row = await conn.fetchrow(_WRITES)
    if row["superuser"] or row["owned"] or row["writable"]:
        raise ConnectorRefused(
            "this login can change the database (it is a superuser, owns a table, or may write to "
            "one); a SQL connection reads through a read-only login only, so nothing was read"
        )


async def check_sql_connection(
    settings: SqlConnectionSettings, *, secret: str | None, connect: Connect = asyncpg.connect
) -> ConnectionTest:
    """*Test connection*: signed in over TLS, and the login is read-only. Nothing is read."""
    try:
        conn = await _open(settings, secret, connect)
        try:
            await _refuse_a_writing_login(conn)
        finally:
            await conn.close()
    except ConnectorRefused as refused:
        return ConnectionTest(ok=False, words=str(refused))
    return ConnectionTest(ok=True, words="Signed in over TLS with a read-only login.")


async def read_sql(
    settings: SqlConnectionSettings,
    read: SqlRead,
    *,
    secret: str | None,
    watermark: str | None = None,
    cursor: str | None = None,
    connect: Connect = asyncpg.connect,
) -> ReadRows:
    """The table's rows (past `cursor` on `watermark`, in its order, when incremental), as text."""
    conn = await _open(settings, secret, connect)
    try:
        await _refuse_a_writing_login(conn)
        async with conn.transaction(readonly=True):
            return await _read(conn, read, watermark, cursor)
    except asyncpg.PostgresError as exc:
        raise ConnectorRefused(
            f"the database refused the read ({type(exc).__name__}): check the table and its "
            "columns; nothing was written"
        ) from exc
    finally:
        await conn.close()


async def _read(conn: Any, read: SqlRead, watermark: str | None, cursor: str | None) -> ReadRows:
    table = _quoted(read.table)
    columns = ", ".join(_quoted(c) for c in read.columns) if read.columns else "*"
    if watermark is not None and read.columns and watermark not in read.columns:
        columns += f", {_quoted(watermark)}"
    sql = f"SELECT {columns} FROM {table}"
    args: list[Any] = []
    if watermark is not None:
        kind = await conn.fetchval(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "WHERE a.attrelid = $1::regclass AND a.attname = $2 AND NOT a.attisdropped",
            table, watermark,
        )  # fmt: skip
        if kind is None or not _TYPE.match(kind):
            raise ConnectorRefused(
                f"the table has no column {watermark!r} to read past; nothing was written"
            )
        if cursor is not None:
            sql += f" WHERE {_quoted(watermark)} > $1::text::{kind}"
            args.append(cursor)
        sql += f" ORDER BY {_quoted(watermark)}"
    sql += f" LIMIT {reads.MAX_ROWS + 1}"
    records = await conn.fetch(sql, *args)
    if len(records) > reads.MAX_ROWS:
        raise ConnectorRefused(
            f"the table holds more than {reads.MAX_ROWS} rows to read, more than one read may "
            "hold; nothing was written (rule 2)"
        )
    names = list(records[0].keys()) if records else await _columns(conn, table, read)
    rows = [{n: as_text(_plain(r[n])) for n in names} for r in records]
    reached = cursor
    if watermark is not None and rows:
        reached = rows[-1][watermark]
    return ReadRows(columns=names, rows=rows, cursor=reached)


def _plain(value: Any) -> Any:
    """A database value as a JSON-like one: a date or time as ISO 8601, a decimal as text."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is not None and not isinstance(value, str | int | float | bool | dict | list):
        return str(value)
    return value


async def _columns(conn: Any, table: str, read: SqlRead) -> list[str]:
    if read.columns:
        return list(read.columns)
    rows = await conn.fetch(
        "SELECT a.attname FROM pg_attribute a WHERE a.attrelid = $1::regclass AND a.attnum > 0 "
        "AND NOT a.attisdropped ORDER BY a.attnum",
        table,
    )
    return [r["attname"] for r in rows]
