"""The S3 connector (L1.9 part 1; ADR-148 decisions 4 and 7; `09_INGEST_STUDIO.md` §2).

A source on an S3 connection reads the CSV or Parquet objects in one folder of the connection's
bucket, and every folder under it, in key order. The folder is a name under the connection's own
prefix, so a source can never read beside it. Their rows land, through `reads.write_snapshot`, as
the source's one CSV file, so everything after is the path every connector source already takes.

**Read-only, and no key.** The reader is given a bucket (`ObjectStore`, two read-only calls of
`pyarrow.fs.FileSystem`); a deployment's is pyarrow's S3 filesystem signed in as its own cloud
identity (`connector_reads.Readers`), and nothing here writes, deletes or copies an object.

**Never truncated silently** (rule 2): the objects are listed and their sizes summed before any is
opened, so a read past the byte cap opens none; each is read against the room left, so an object
rewritten larger after the listing is stopped while read; a Parquet object's rows are counted from
its footer before any is read. Past any cap the read is refused whole; nothing is written.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from decimal import Decimal
from typing import Any, Protocol

import pyarrow.fs as pa_fs
import pyarrow.parquet as pq

from schemas.sources import S3ConnectionSettings, S3Read

from . import reads
from .reads import ConnectorRefused, ReadOverCap, ReadRows


class ObjectStore(Protocol):
    """What the reader asks of a bucket: the two read-only calls of `pyarrow.fs.FileSystem`
    (`get_file_info` takes a selector, answering a list, or a path, answering one)."""

    def get_file_info(self, selector_or_path: Any, /) -> Any: ...

    def open_input_stream(self, path: str, /) -> Any: ...


#: The most objects one read may take; past it the read is refused whole (rule 2).
MAX_OBJECTS = 1_000
_SUFFIXES = {"csv": (".csv",), "parquet": (".parquet", ".parq")}
_FORMAT_WORDS = {"csv": "CSV", "parquet": "Parquet"}


def refused_by_store(error: OSError) -> ConnectorRefused:
    """What S3 said, in fixed words: never the store's own message, which names hosts and keys.
    Judged by the AWS error code pyarrow quotes (`AWS Error ACCESS_DENIED during …`) alone, never by
    words anywhere in the message, which also holds the bucket and key (a folder named
    `forbidden/` is no refusal; the lane review of L1.9)."""
    found = re.search(r"AWS Error ([A-Z_]+)", str(error))
    code = found.group(1) if found else ""
    if code in {"ACCESS_DENIED", "INVALID_ACCESS_KEY_ID", "SIGNATURE_DOES_NOT_MATCH"}:
        return ConnectorRefused(
            "the bucket refused the read (access denied): the deployment's cloud role may not read "
            "it; nothing was read"
        )
    if code in {"NO_SUCH_BUCKET", "RESOURCE_NOT_FOUND"}:
        return ConnectorRefused(MISSING_BUCKET)
    return ConnectorRefused(
        f"the bucket could not be read ({type(error).__name__}); nothing was read"
    )


MISSING_BUCKET = "the bucket does not exist; nothing was read"


def list_folder(fs: ObjectStore, bucket: str, base: str, *, recursive: bool) -> list[Any]:
    """The folder's listing, refused in words. An empty one is checked against the bucket: a listing
    answers a bucket that does not exist as empty (found on SeaweedFS, L1.9). The bucket is asked
    for only then, since asking needs `s3:ListBucket` on the whole bucket, which a role limited to
    a prefix may not hold (the lane review): such a role's empty folder stays an empty folder."""
    try:
        found = list(
            fs.get_file_info(pa_fs.FileSelector(base, recursive=recursive, allow_not_found=True))
        )
    except OSError as error:
        raise refused_by_store(error) from error
    if not found:
        try:
            missing = fs.get_file_info(bucket).type == pa_fs.FileType.NotFound
        except OSError:
            missing = False  # not ours to ask: the folder is empty, as far as this role can see
        if missing:
            raise ConnectorRefused(MISSING_BUCKET)
    return found


def _hidden(part: str) -> bool:
    """A `.`- or `_`-name: a part-file, a sync tool's, or a job's (`_temporary/`, `_SUCCESS`)."""
    return part.startswith((".", "_"))


def _objects(
    fs: ObjectStore, settings: S3ConnectionSettings, read: S3Read
) -> tuple[str, list[pa_fs.FileInfo]]:
    """The objects to read, in key order, and the folder's name for the words: every object of the
    read's format under the folder, a hidden one (a `.`- or `_`-name anywhere in its key below the
    folder) never."""
    folder = f"{settings.prefix}{read.folder}"
    base = f"{settings.bucket}/{folder}".rstrip("/")
    found = list_folder(fs, settings.bucket, base, recursive=True)
    suffixes = _SUFFIXES[read.format]
    chosen = [
        info
        for info in found
        if info.type == pa_fs.FileType.File
        and info.path.startswith(base + "/")
        and not any(_hidden(p) for p in info.path[len(base) + 1 :].split("/"))
        and info.base_name.lower().endswith(suffixes)
    ]
    chosen.sort(key=lambda i: i.path)
    where = f"s3://{settings.bucket}/{folder}"
    if not chosen:
        raise ConnectorRefused(
            f"there is no {_FORMAT_WORDS[read.format]} object under {where}; nothing was written"
        )
    if len(chosen) > MAX_OBJECTS:
        raise ReadOverCap(
            f"{where} holds more than {MAX_OBJECTS} objects, more than one read may take; nothing "
            "was written (rule 2)"
        )
    return where, chosen


def _over_bytes(where: str) -> ConnectorRefused:
    return ReadOverCap(
        f"the objects under {where} come to more than {reads.MAX_BYTES} bytes, more than one read "
        "may take; nothing was written (rule 2)"
    )


def _over_rows(where: str) -> ConnectorRefused:
    return ReadOverCap(
        f"the objects under {where} hold more than {reads.MAX_ROWS} rows, more than one read may "
        "hold; nothing was written (rule 2)"
    )


def _body(fs: ObjectStore, info: pa_fs.FileInfo, room: int, where: str) -> bytes:
    """One object's bytes, read no further than `room` + 1, so one past the cap is never whole."""
    try:
        with fs.open_input_stream(info.path) as handle:
            body = bytes(handle.read(room + 1))
    except OSError as error:
        raise refused_by_store(error) from error
    if len(body) > room:
        raise _over_bytes(where)
    return body


def _csv_records(body: bytes, key: str) -> list[dict[str, Any]]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConnectorRefused(f"{key} is not UTF-8 text; nothing was written") from exc
    rows = csv.reader(io.StringIO(text, newline=""))
    header = next(rows, None)
    if not header:
        return []
    seen: set[str] = set()
    for name in header:
        if name in seen:
            raise ConnectorRefused(f"{key} names the column {name!r} twice; nothing was written")
        seen.add(name)
    records: list[dict[str, Any]] = []
    for number, values in enumerate(rows, start=2):
        if not values:
            continue
        if len(values) > len(header):
            raise ConnectorRefused(
                f"row {number} of {key} has more values than its header names; nothing was written"
            )
        records.append(dict(zip(header, values, strict=False)))
    return records


def cell(value: Any) -> Any:
    """A Parquet value as `reads.as_text` takes it: a date or time as ISO 8601, a decimal as
    written, bytes refused (a cell is text), everything else as it is."""
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes | bytearray):
        raise ConnectorRefused("a Parquet column holds binary values, which a cell cannot; "
                               "nothing was written")  # fmt: skip
    if isinstance(value, list):
        return [cell(v) for v in value]
    if isinstance(value, dict):
        return {k: cell(v) for k, v in value.items()}
    return value


def _parquet_rows(body: bytes, key: str, room: int, where: str) -> tuple[list[dict[str, Any]], int]:
    """The object's rows, and how many bytes they take decoded. Read a row group at a time, each
    measured decoded before any becomes a row: a small file whose values repeat (dictionary
    encoded, then compressed) can unpack to far more than the byte cap (the lane review, finding
    11), so the read stops at the row group that passes it, never holding the whole."""
    try:
        parquet = pq.ParquetFile(io.BytesIO(body))
        groups = []
        for group in range(parquet.num_row_groups):
            table = parquet.read_row_group(group)
            room -= table.nbytes
            if room < 0:
                raise _over_bytes(where)
            groups.append(table)
    except ConnectorRefused:
        raise
    except Exception as exc:  # pyarrow's own errors, of several kinds
        raise ConnectorRefused(f"{key} is not a Parquet file pyarrow can read; nothing was "
                               "written") from exc  # fmt: skip
    rows = [{k: cell(v) for k, v in row.items()} for t in groups for row in t.to_pylist()]
    return rows, sum(t.nbytes for t in groups)


def _parquet_count(body: bytes, key: str) -> tuple[int, int]:
    """A Parquet object's rows and its uncompressed size, from its footer, before any row is read:
    a small, well-compressed file can unpack to far more than the byte cap (the lane review)."""
    try:
        meta = pq.ParquetFile(io.BytesIO(body)).metadata
        size = sum(meta.row_group(g).total_byte_size for g in range(meta.num_row_groups))
        return int(meta.num_rows), int(size)
    except Exception as exc:
        raise ConnectorRefused(f"{key} is not a Parquet file pyarrow can read; nothing was "
                               "written") from exc  # fmt: skip


def read_s3(fs: ObjectStore, settings: S3ConnectionSettings, read: S3Read) -> ReadRows:
    """Every row of the read's objects, their columns in first-seen order."""
    where, objects = _objects(fs, settings, read)
    if sum(i.size or 0 for i in objects) > reads.MAX_BYTES:
        raise _over_bytes(where)
    room = reads.MAX_BYTES
    bodies: list[tuple[str, bytes]] = []
    for info in objects:
        body = _body(fs, info, room, where)
        room -= len(body)
        bodies.append((info.path.split("/", 1)[1], body))
    records: list[dict[str, Any]] = []
    if read.format == "parquet":
        counts = [_parquet_count(body, key) for key, body in bodies]
        if sum(rows for rows, _size in counts) > reads.MAX_ROWS:
            raise _over_rows(where)
        if sum(size for _rows, size in counts) > reads.MAX_BYTES:
            raise _over_bytes(where)
        decoded = reads.MAX_BYTES
        for key, body in bodies:
            found, used = _parquet_rows(body, key, decoded, where)
            decoded -= used
            records += found
    else:
        for key, body in bodies:
            records += _csv_records(body, key)
            if len(records) > reads.MAX_ROWS:
                raise _over_rows(where)
    for record in records:
        for name, value in record.items():
            if isinstance(value, list | dict):
                record[name] = json.loads(json.dumps(value, default=str))
    return reads.tabulate(records, where)
