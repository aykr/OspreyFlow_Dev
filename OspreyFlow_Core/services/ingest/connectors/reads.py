"""Phase 9's connectors beyond CSV: what each reads, and where a read lands (`06_DECISIONS.md`
ADR-140 Amendment 13; the redesign's phase 9).

A SQL, API or JSON source is read into **rows of text**, and each read lands **whole** as the
source's one CSV file in the dataset's folder of the ingest root, `uploaded/<dataset>/<source>.csv`,
written to a temporary name and renamed into place, so a run never reads half a file. Everything
after that is the path every file source already takes: the source's folder watch runs each deployed
pipeline on the new file (its name, size and time are new), a run keeps the rows it read as its own
load's raw rows, and an incremental watermark, the ingest folder's confinement and the rule gate
apply as built.

**Nothing truncated silently** (rule 2): a read holding more than `MAX_ROWS` rows, or more than
`MAX_PAGES` pages, is refused whole, in words; nothing is written. **No expression anywhere** (rule
8): a records path is dotted names, a SQL table a name; the schemas refuse anything else.

A value is written as text: a number or `true`/`false` as JSON writes it, a nested object or list as
compact JSON, an empty or missing value as an empty cell.
"""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from schemas.sources import ApiConnectionSettings, ApiRead, JsonRead

#: The most rows one read may hold; past it the read is refused whole (rule 2).
MAX_ROWS = 500_000
#: The most pages one API read follows.
MAX_PAGES = 1_000
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ConnectorRefused(Exception):
    """A read refused in words; nothing was written. Never names a secret's value."""


@dataclass
class ReadRows:
    columns: list[str]
    rows: list[dict[str, str | None]]
    #: For an incremental read: the highest watermark value read, as text.
    cursor: str | None = None
    notes: list[str] = field(default_factory=list)


def as_text(value: Any) -> str | None:
    """A value as a cell: text kept, a number or a truth value as JSON writes it, a nested value as
    compact JSON, nothing as an empty cell."""
    if value is None:
        return None
    if isinstance(value, str):
        return value if value != "" else None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return json.dumps(value)
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _at(document: Any, path: str | None, where: str) -> list[Any]:
    found = document
    for name in path.split(".") if path else []:
        if not isinstance(found, dict) or name not in found:
            raise ConnectorRefused(f"{where} has no records at {path!r}; nothing was written")
        found = found[name]
    if not isinstance(found, list):
        raise ConnectorRefused(
            f"{where} does not hold a list of records at {path or 'its top level'!r}; "
            "nothing was written"
        )
    return found


def tabulate(records: Sequence[Any], where: str) -> ReadRows:
    """Records (each an object) as rows, their columns in first-seen order."""
    if len(records) > MAX_ROWS:
        raise ConnectorRefused(
            f"{where} holds more than {MAX_ROWS} rows, more than one read may hold; nothing was "
            "written (rule 2)"
        )
    columns: list[str] = []
    for number, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ConnectorRefused(
                f"record {number} of {where} is not an object; nothing was written"
            )
        for key in record:
            if key not in columns:
                columns.append(str(key))
    rows = [{c: as_text(r.get(c)) for c in columns} for r in records]
    return ReadRows(columns=columns, rows=rows)


# --- JSON files ----------------------------------------------------------------------------------


def read_json(files: Sequence[tuple[str, bytes]], read: JsonRead) -> ReadRows:
    """The records of each JSON file, in the order given, at the source's records path."""
    records: list[Any] = []
    for name, content in files:
        try:
            document = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectorRefused(f"{name} is not JSON text; nothing was written") from exc
        records += _at(document, read.records_at, name)
        if len(records) > MAX_ROWS:
            break
    return tabulate(records, "the JSON files")


# --- an API --------------------------------------------------------------------------------------


def check_egress(url: str, allowed_hosts: Collection[str]) -> str:
    """The URL's host, if the deployment's egress allow-list names it; refused in words
    otherwise."""
    host = (urlsplit(url).hostname or "").lower()
    if host not in {h.strip().lower() for h in allowed_hosts if h.strip()}:
        raise ConnectorRefused(
            f"{host or 'that address'} is not on this deployment's egress allow-list: ask an "
            "operator to add it (OSPREY_CONNECTOR_EGRESS); nothing was read"
        )
    return host


def egress_allow_list() -> list[str]:
    """`OSPREY_CONNECTOR_EGRESS`: the hosts an API connection may reach, comma-separated; set by an
    operator in `deployment.env`, never through a route."""
    return [h for h in os.environ.get("OSPREY_CONNECTOR_EGRESS", "").split(",") if h.strip()]


async def read_api(
    settings: ApiConnectionSettings,
    read: ApiRead,
    *,
    secret: str | None,
    allowed_hosts: Collection[str],
    transport: httpx.AsyncBaseTransport | None = None,
) -> ReadRows:
    """Every page of the endpoint's records. A refusal, an error or records missing where the read
    says they are is refused in words: never read as no rows."""
    url = settings.base_url.rstrip("/") + read.path
    check_egress(url, allowed_hosts)
    origin = _origin(url)
    headers = {"Accept": "application/json"}
    if settings.auth == "bearer":
        if not secret:
            raise ConnectorRefused("the connection's secret is not set; nothing was read")
        headers["Authorization"] = f"Bearer {secret}"
    records: list[Any] = []
    async with httpx.AsyncClient(
        transport=transport, timeout=_TIMEOUT, headers=headers, follow_redirects=False
    ) as client:
        page, next_url = 1, url
        for _ in range(MAX_PAGES):
            params = {settings.page_param: str(page)} if settings.pagination == "page" else None
            document = await _get(client, next_url, params)
            found = _at(document, read.records_at, "the API's answer")
            records += found
            if len(records) > MAX_ROWS:
                break
            if settings.pagination == "page":
                if not found:
                    break
                page += 1
            elif settings.pagination == "next_link":
                link = _next_link(document, settings.next_at)
                if link is None:
                    break
                next_url = urljoin(next_url, link)
                if _origin(next_url) != origin:
                    # Scheme and port as well as host: a next link over plain HTTP would carry the
                    # bearer secret in clear (the lane review of L1.6).
                    raise ConnectorRefused(
                        "the API named a next page at another address (host, scheme or port); it "
                        "was not followed and nothing was written"
                    )
            else:
                break
        else:
            raise ConnectorRefused(
                f"the API gave more than {MAX_PAGES} pages, more than one read may follow; nothing "
                "was written (rule 2)"
            )
    return tabulate(records, "the API's answer")


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    port = parts.port or {"https": 443, "http": 80}.get(parts.scheme)
    return parts.scheme, (parts.hostname or "").lower(), port


def _next_link(document: Any, path: str | None) -> str | None:
    found = document
    for name in (path or "").split("."):
        if not isinstance(found, dict):
            return None
        found = found.get(name)
    return found if isinstance(found, str) and found else None


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, str] | None) -> Any:
    try:
        response = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise ConnectorRefused(
            f"the API could not be reached ({type(exc).__name__}); nothing was read"
        ) from exc
    if response.status_code in (401, 403):
        raise ConnectorRefused(
            f"the API refused the sign-in ({response.status_code}): check the connection's secret; "
            "nothing was read"
        )
    if response.status_code != 200:
        raise ConnectorRefused(
            f"the API answered {response.status_code}, not 200; nothing was written"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ConnectorRefused("the API's answer is not JSON; nothing was written") from exc


# --- where a read lands --------------------------------------------------------------------------


def _held_rows(target: Path, columns: list[str]) -> list[list[str]]:
    """The rows the source's file already holds, refused if its columns are not this read's."""
    with target.open(encoding="utf-8", newline="") as handle:
        held = list(csv.reader(handle))
    if not held:
        return []
    if held[0] != columns:
        raise ConnectorRefused(
            "the table's columns changed since its last read, so new rows cannot be added to its "
            "file; nothing was written. Read it whole once (a snapshot refresh) to start afresh"
        )
    return held[1:]


def write_snapshot(rows: ReadRows, folder: Path, name: str, *, keep_earlier: bool = False) -> Path:
    """The read as `<folder>/<name>.csv`, written to a temporary file beside it and renamed into
    place, so a run reading the file sees the last read or this one, never half of either.

    `keep_earlier` (an incremental read; the lane review of L1.6): the file keeps every row it held
    and gains this read's, since an earlier read's rows may not have been loaded yet (a paused
    watch, a failed run), and each run's own watermark reads only what it has not loaded. A read
    that finds nothing leaves the file as it was. Otherwise the file is this read, whole."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{name}.csv"
    earlier: list[list[str]] = []
    if keep_earlier and target.exists():
        if not rows.rows:
            return target
        earlier = _held_rows(target, rows.columns)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(rows.columns)
    writer.writerows(earlier)
    for row in rows.rows:
        writer.writerow(["" if row.get(c) is None else row[c] for c in rows.columns])
    if len(earlier) + len(rows.rows) > MAX_ROWS:
        raise ConnectorRefused(
            f"the source's file would hold more than {MAX_ROWS} rows; nothing was written (rule 2)"
        )
    handle, temporary = tempfile.mkstemp(prefix=".read-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as out:
            out.write(buffer.getvalue())
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target
