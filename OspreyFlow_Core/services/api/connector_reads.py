"""Reading a SQL, API or JSON source into its one file in the dataset's folder (`06_DECISIONS.md`
ADR-140 Amendment 13; the redesign's phase 9).

A non-file source's `location` is its own file, `<ingest root>/uploaded/<dataset>/<name>.csv`. Each
read (at registration, then each *Refresh now*) writes that file whole with the rows it found, so
the source's pipelines run on it exactly as on any file: by its folder watch, by *Run now*, with the
run's raw rows, watermark and rule gate as built. An incremental SQL source's read takes only rows
past its cursor, so the file then holds only what is new.

**Secrets** are the deployment's: a connection names one, and its value is read here from
`OSPREY_CONNECTION_SECRET_<NAME>` (set in `deployment.env` by an operator), never stored, logged,
audited or sent back. **Egress**: an API connection reaches only hosts on `OSPREY_CONNECTOR_EGRESS`.
"""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from services.ingest.connectors.reads import (
    ConnectorRefused,
    ReadRows,
    check_egress,
    egress_allow_list,
    read_api,
    read_json,
    write_snapshot,
)
from services.ingest.connectors.sql_connector import Connect, check_sql_connection, read_sql

from schemas.sources import (
    ApiConnectionSettings,
    ApiRead,
    Connection,
    ConnectionTest,
    JsonRead,
    SourceTable,
    SqlConnectionSettings,
    SqlRead,
)

from .ingest_sources import UPLOAD_SUBDIR, ingest_root, is_inside

#: A non-file source's own name for its file: plain, lower case, no path.
SOURCE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def secret_of(name: str | None) -> str | None:
    """A connection's secret, by its name, from the deployment's environment."""
    return os.environ.get(f"OSPREY_CONNECTION_SECRET_{name}") if name else None


@dataclass
class Readers:
    """What a read reaches, so a test can stand a fixture in for each (rule 15: each refuses what
    the real one refuses)."""

    sql_connect: Connect = asyncpg.connect
    http_transport: httpx.AsyncBaseTransport | None = None
    allowed_hosts: Collection[str] | None = None

    def hosts(self) -> Collection[str]:
        return egress_allow_list() if self.allowed_hosts is None else self.allowed_hosts


def source_file(dataset_id: str, name: str, root: Path | None = None) -> Path:
    """Where a non-file source's reads land: its one file in the dataset's uploaded folder."""
    if not SOURCE_NAME.match(name):
        raise ConnectorRefused(
            "a source read through a connection is named in lower-case letters, digits, '-' and "
            "'_' only, so its file can be found"
        )
    root = root if root is not None else ingest_root()
    return root / UPLOAD_SUBDIR / dataset_id / f"{name}.csv"


def _json_files(dataset_id: str, pattern: str, root: Path) -> list[tuple[str, bytes]]:
    found: list[tuple[str, bytes]] = []
    for folder in (root / dataset_id, root / UPLOAD_SUBDIR / dataset_id):
        if not folder.is_dir():
            continue
        for candidate in sorted(folder.iterdir(), key=lambda p: p.name):
            resolved = candidate.resolve()
            if (
                fnmatch.fnmatchcase(candidate.name, pattern)
                and is_inside(folder, resolved)
                and resolved.is_file()
            ):
                found.append((candidate.name, resolved.read_bytes()))
    if not found:
        raise ConnectorRefused(
            f"no file in the dataset's folder matches {pattern!r}; nothing was written"
        )
    return found


async def read_rows(
    source: SourceTable | Any,
    connection: Connection,
    *,
    dataset_id: str,
    cursor: str | None,
    readers: Readers,
    root: Path,
) -> ReadRows:
    """The rows one read of `source` finds, through its connection."""
    settings, read = connection.settings, source.read
    if isinstance(settings, SqlConnectionSettings) and isinstance(read, SqlRead):
        refresh = getattr(source, "refresh", None)
        watermark = (
            refresh.watermark_column
            if refresh is not None and refresh.mode == "incremental"
            else None
        )
        return await read_sql(
            settings, read, secret=secret_of(settings.secret), watermark=watermark,
            cursor=cursor if watermark else None, connect=readers.sql_connect,
        )  # fmt: skip
    if isinstance(settings, ApiConnectionSettings) and isinstance(read, ApiRead):
        return await read_api(
            settings, read, secret=secret_of(settings.secret), allowed_hosts=readers.hosts(),
            transport=readers.http_transport,
        )  # fmt: skip
    if connection.kind == "json" and isinstance(read, JsonRead):
        return read_json(_json_files(dataset_id, read.pattern, root), read)
    raise ConnectorRefused(
        f"the source's read is not one a {connection.kind} connection takes; nothing was read"
    )


async def read_into_file(
    source: SourceTable | Any,
    connection: Connection,
    *,
    dataset_id: str,
    name: str,
    cursor: str | None,
    readers: Readers,
    root: Path | None = None,
) -> tuple[ReadRows, Path]:
    """One read, landed as the source's file; returns the rows and the file. An incremental read
    adds its rows to the rows the file holds (none of which may have been loaded yet) and leaves the
    file as it was when it finds nothing; any other read is the file, whole (the lane review of
    L1.6)."""
    root = root if root is not None else ingest_root()
    target = source_file(dataset_id, name, root)
    rows = await read_rows(source, connection, dataset_id=dataset_id, cursor=cursor,
                           readers=readers, root=root)  # fmt: skip
    return rows, write_snapshot(rows, target.parent, name, keep_earlier=incremental(source))


def incremental(source: SourceTable | Any) -> bool:
    """Whether the source is a SQL table read past a watermark."""
    refresh = getattr(source, "refresh", None)
    return (
        isinstance(getattr(source, "read", None), SqlRead)
        and refresh is not None
        and refresh.mode == "incremental"
        and bool(refresh.watermark_column)
    )


async def check_connection(connection: Connection, readers: Readers) -> ConnectionTest:
    """*Test connection*: a SQL login signed in over TLS and found read-only; an API's host on the
    allow-list and its secret set. Nothing is read."""
    settings = connection.settings
    if isinstance(settings, SqlConnectionSettings):
        return await check_sql_connection(
            settings, secret=secret_of(settings.secret), connect=readers.sql_connect
        )
    if isinstance(settings, ApiConnectionSettings):
        try:
            check_egress(settings.base_url, readers.hosts())
        except ConnectorRefused as refused:
            return ConnectionTest(ok=False, words=str(refused))
        if settings.auth == "bearer" and not secret_of(settings.secret):
            return ConnectionTest(
                ok=False, words=f"the secret {settings.secret} is not set in this deployment"
            )
        return ConnectionTest(ok=True, words="The host is allowed and the secret is set.")
    return ConnectionTest(ok=True, words="Files in the ingest folder: nothing to sign in to.")
