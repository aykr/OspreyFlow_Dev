"""ClickHouse over its HTTP interface, with every value sent as a typed query parameter.

No driver: `httpx` (already a dependency) speaks ClickHouse's HTTP protocol directly, and a value
never enters the SQL text — each `?` the adapter writes becomes `{pN:Type}`, with the value sent
as `param_pN` beside the query, which the server parses as data of that type (ClickHouse's own
"queries with parameters"). That is the property the DuckDB adapter's `?` binding gives it, kept
whole: an analyst's search term or a property value cannot change what the query is.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx


class ClickHouseError(RuntimeError):
    """The server refused a statement; its own message, unchanged."""


def _escaped(text: str) -> str:
    # A parameter's value is read in ClickHouse's escaped (TSV) form: a backslash, tab or newline
    # in the value must be written escaped, or the server reads a different value.
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def utc_text(moment: datetime) -> str:
    """A time as the `DateTime64(6, 'UTC')` columns read it; a naive time is taken as UTC."""
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def _quoted(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _typed(value: object) -> tuple[str, str]:
    """The ClickHouse type a value is declared as, and its text."""
    if value is None:
        return "Nullable(String)", "\\N"
    if isinstance(value, bool):
        return "Bool", "true" if value else "false"
    if isinstance(value, int):
        return "Int64", str(value)
    if isinstance(value, float):
        return "Float64", repr(value)
    if isinstance(value, datetime):
        return "DateTime64(6, 'UTC')", utc_text(value)
    if isinstance(value, str):
        return "String", _escaped(value)
    if isinstance(value, list | tuple) and all(isinstance(v, str) for v in value):
        return "Array(String)", _escaped("[" + ",".join(_quoted(v) for v in value) + "]")
    raise TypeError(f"no ClickHouse parameter type for {type(value).__name__}")


def bind(sql: str, params: Sequence[object]) -> tuple[str, dict[str, str]]:
    """`?` placeholders, in order, to typed `{pN:Type}` parameters and their values.

    The statements this adapter writes never hold a `?` inside a literal, so every `?` is a
    placeholder; a count that does not match is a programming error and refused."""
    pieces = sql.split("?")
    if len(pieces) - 1 != len(params):
        raise ValueError(f"{len(pieces) - 1} placeholders but {len(params)} values")
    out = [pieces[0]]
    values: dict[str, str] = {}
    for n, (value, rest) in enumerate(zip(params, pieces[1:], strict=True)):
        kind, text = _typed(value)
        out.append(f"{{p{n}:{kind}}}{rest}")
        values[f"param_p{n}"] = text
    return "".join(out), values


@dataclass(frozen=True)
class ClickHouseSettings:
    url: str
    user: str
    password: str
    database: str

    @classmethod
    def from_env(cls, database: str = "default") -> ClickHouseSettings:
        host = os.environ.get("CLICKHOUSE_HOST", "localhost")
        port = os.environ.get("CLICKHOUSE_HTTP_PORT", "8123")
        return cls(
            url=f"http://{host}:{port}/",
            user=os.environ.get("CLICKHOUSE_USER", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
            database=os.environ.get("CLICKHOUSE_DATABASE", database),
        )


class ClickHouseClient:
    def __init__(self, settings: ClickHouseSettings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=60.0)

    @property
    def database(self) -> str:
        return self._settings.database

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _post(
        self, body: str | bytes, query: dict[str, str], *, database: str | None
    ) -> str:
        params = {
            **({"database": database} if database else {}),
            "output_format_json_quote_64bit_integers": "0",
            "date_time_input_format": "best_effort",
            **query,
        }
        response = await self._http.post(
            self._settings.url,
            params=params,
            content=body,
            auth=(self._settings.user, self._settings.password),
        )
        if response.status_code != 200:
            raise ClickHouseError(response.text.strip())
        return response.text

    async def command(
        self, sql: str, params: Sequence[object] = (), *, database: str | None = ""
    ) -> None:
        """A statement with no rows back. `database=None` runs it outside any database (to make
        or drop one); the default is the client's own."""
        text, values = bind(sql, params)
        await self._post(text, values, database=self._db(database))

    async def rows(self, sql: str, params: Sequence[object] = ()) -> list[list[Any]]:
        text, values = bind(sql, params)
        body = await self._post(f"{text} FORMAT JSONCompact", values, database=self._db(""))
        return list(json.loads(body)["data"])

    async def insert(self, table: str, records: Sequence[dict[str, object]]) -> None:
        if not records:
            return
        lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
        await self._post(
            lines.encode("utf-8"),
            {"query": f"INSERT INTO {table} FORMAT JSONEachRow"},
            database=self._db(""),
        )

    def _db(self, database: str | None) -> str | None:
        return self._settings.database if database == "" else database
