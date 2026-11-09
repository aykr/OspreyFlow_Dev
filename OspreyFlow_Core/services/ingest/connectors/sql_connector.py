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

import asyncio
import re
import ssl
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import asyncpg

from schemas.sources import SQL_COLUMN, ConnectionTest, SqlConnectionSettings, SqlRead

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
    """Each part of a name as a quoted identifier, any `"` in it doubled (the schema already
    refuses one; this holds whatever the caller passes)."""
    return ".".join('"' + part.replace('"', '""') + '"' for part in name.split("."))


class NamedTls(ssl.SSLContext):
    """A client TLS context that checks the server's certificate against `server_name` whatever
    address the connection was made to: the connection goes to the address the host check passed,
    and the certificate must still name the host the administrator wrote (ADR-140 Amendment 15)."""

    server_name: str | None = None

    def wrap_bio(  # type: ignore[override]
        self, incoming: Any, outgoing: Any, server_side: bool = False,
        server_hostname: str | None = None, session: Any = None,
    ) -> ssl.SSLObject:  # fmt: skip
        return super().wrap_bio(
            incoming, outgoing, server_side, self.server_name or server_hostname, session
        )


def _tls(settings: SqlConnectionSettings) -> ssl.SSLContext | str:
    """verify-full: the system's trust store and the connection's own CA, if it names one, with the
    certificate and its name checked; else TLS asked for without either."""
    if settings.tls != "verify-full":
        return "require"
    context = NamedTls(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs()
    if settings.ca_certificate:
        context.load_verify_locations(cadata=settings.ca_certificate)
    context.server_name = settings.host.rstrip(".")
    return context


#: Whether a TCP connection to (address, port) can be opened now; nothing is sent on it.
Reach = Callable[[str, int], Awaitable[bool]]
#: How long the reachability check waits for one address.
REACH_SECONDS = 5.0


async def tcp_reaches(address: str, port: int) -> bool:
    """A plain TCP connection opened and closed at once: nothing, not even TLS, is sent on it."""
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(address, port), REACH_SECONDS
        )
    except (OSError, TimeoutError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True


async def _open(
    settings: SqlConnectionSettings, secret: str | None, connect: Connect,
    addresses: Sequence[str] | None = None, reach: Reach = tcp_reaches,
) -> Any:  # fmt: skip
    """Signed in at one address. With several checked addresses (in the resolver's order), each is
    first only reached over plain TCP, nothing sent, and the first that answers is the one address
    asyncpg is given; whatever then fails (TLS, the certificate, the sign-in, a timeout or a reset
    after the password went) is final, so no second server is ever sent the password (the
    orchestrator's review of Amendment 15, item 4, and the lane review that followed). With no
    addresses (a fixture's own check), by the host's name."""
    if not secret:
        raise ConnectorRefused(
            "the connection's secret is not set, or not declared in osprey.yaml's "
            "connectors.secrets; nothing was read"
        )
    candidates = list(addresses or [])
    host = settings.host
    if len(candidates) == 1:
        host = candidates[0]
    elif candidates:
        for candidate in candidates:
            if await reach(candidate, settings.port):
                host = candidate
                break
        else:
            raise ConnectorRefused(
                "the database could not be reached at any address its name resolves to; nothing "
                "was read"
            )
    try:
        return await connect(
            host=host, port=settings.port, user=settings.user, password=secret,
            database=settings.database, ssl=_tls(settings), timeout=15,
            # Every statement bounded, and the session read-only from its first statement (the
            # orchestrator's review of L1.6).
            server_settings={"statement_timeout": STATEMENT_TIMEOUT_MS,
                             "default_transaction_read_only": "on"},
        )  # fmt: skip
    except ssl.SSLCertVerificationError as exc:
        raise ConnectorRefused(
            "the database's certificate could not be verified (a CA this connection does not "
            "trust, or a name the certificate does not hold); nothing was read"
        ) from exc
    except (OSError, asyncpg.PostgresError, ConnectionError) as exc:
        words = str(exc).lower()
        if isinstance(exc, ssl.SSLError) or "ssl" in words or "tls" in words:
            raise ConnectorRefused(
                "the database would not speak TLS, which every SQL connection asks for; "
                "nothing was read"
            ) from exc
        if isinstance(
            exc, asyncpg.InvalidPasswordError | asyncpg.InvalidAuthorizationSpecificationError
        ):
            raise ConnectorRefused(
                "the database refused the sign-in: check the connection's login and secret; "
                "nothing was read"
            ) from exc
        if isinstance(exc, asyncpg.PostgresError):
            raise ConnectorRefused(
                f"the database refused the connection ({type(exc).__name__}); nothing was read"
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
    settings: SqlConnectionSettings, *, secret: str | None, connect: Connect = asyncpg.connect,
    addresses: Sequence[str] | None = None, reach: Reach = tcp_reaches,
) -> ConnectionTest:  # fmt: skip
    """*Test connection*: signed in over TLS, and the login is read-only. Nothing is read."""
    try:
        conn = await _open(settings, secret, connect, addresses, reach)
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
    addresses: Sequence[str] | None = None,
    reach: Reach = tcp_reaches,
) -> ReadRows:
    """The table's rows (past `cursor` on `watermark`, in its order, when incremental), as text."""
    if watermark is not None and not re.fullmatch(SQL_COLUMN, watermark):
        raise ConnectorRefused("the watermark column is not a plain column name; nothing was read")
    conn = await _open(settings, secret, connect, addresses, reach)
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


#: The two columns the server adds to a read: each row's size, and the running total to it.
_ROW_BYTES, _TAKEN = '"osprey read row bytes"', '"osprey read bytes taken"'


async def _read(conn: Any, read: SqlRead, watermark: str | None, cursor: str | None) -> ReadRows:
    table = _quoted(read.table)
    names = list(read.columns) if read.columns else await _columns(conn, table, read)
    if watermark is not None and watermark not in names:
        names.append(watermark)
    args: list[Any] = []
    where = order = ""
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
            where = f" WHERE {_quoted(watermark)} > $1::text::{kind}"
            args.append(cursor)
        order = f"ORDER BY {_quoted(watermark)} "
    cap = reads.MAX_BYTES
    args.append(cap)
    limit = f"${len(args)}::bigint"
    # The byte cap is kept by the server, before any row's values are sent (rule 2; the independent
    # review of L1.6): each row's size is its text in bytes as the database writes it, with a
    # running total in the read's own order. A row whose total is past the cap is sent without its
    # values, so the read refuses at the first such row having held no more than the cap; nothing
    # past it is read, since the cursor stops there (no filter on the total, which would make the
    # server scan the whole table looking for rows to send, the lane review of L1.8). The database's
    # count is close to the file's, not equal (`t` for `true`, its own date format, its own
    # encoding), so the read also counts each row in UTF-8 bytes as the file will hold it, and
    # refuses on either.
    columns = ", ".join(_quoted(n) for n in names)
    size = f"octet_length(ROW({columns})::text)"
    inner = (
        f"SELECT {columns}, {size} AS {_ROW_BYTES}, "
        f"sum({size}) OVER ({order}ROWS UNBOUNDED PRECEDING) AS {_TAKEN} FROM {table}{where}"
    )
    shown = ", ".join(
        f"CASE WHEN s.{_TAKEN} <= {limit} THEN s.{_quoted(n)} END AS {_quoted(n)}" for n in names
    )
    sql = f"SELECT {shown}, s.{_TAKEN} FROM ({inner}) AS s"
    if watermark is not None:
        sql += f" ORDER BY s.{_quoted(watermark)}, s.{_TAKEN}"
    sql += f" LIMIT {reads.MAX_ROWS + 1}"
    over_bytes = ConnectorRefused(
        f"the table's rows come to more than {cap} bytes, more than one read may take; nothing "
        "was written (rule 2)"
    )
    # Taken through a cursor and stopped at either cap as it is passed, so a table over the cap is
    # never fetched whole (rule 2; the orchestrator's second review). Each row is checked before it
    # is held, in bytes (UTF-8) as the file will hold it, as well as by the server's own count.
    rows: list[dict[str, str | None]] = []
    taken = 0
    async for record in conn.cursor(sql, *args, prefetch=500):
        if record[_TAKEN.strip('"')] > cap:
            raise over_bytes
        row = {n: as_text(_plain(record[n])) for n in names}
        taken += sum(len(v.encode("utf-8")) for v in row.values() if v)
        if taken > cap:
            raise over_bytes
        if len(rows) == reads.MAX_ROWS:
            raise ConnectorRefused(
                f"the table holds more than {reads.MAX_ROWS} rows to read, more than one read "
                "may hold; nothing was written (rule 2)"
            )
        rows.append(row)
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
