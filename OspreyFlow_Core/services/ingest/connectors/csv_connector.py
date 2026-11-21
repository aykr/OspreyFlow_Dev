"""Generic CSV connector — one of the "CSV, JSON and
generic delimited" formats scoped for v1, scoped here to CSV. Every connector yields the
same `Iterable[Mapping[str, str]]` row shape the engine consumes, so a
second format is an additional connector module, not a change to
`services/ingest/engine.py`.
"""

from __future__ import annotations

import csv
import itertools
from collections.abc import Iterator
from pathlib import Path


def read_csv(
    path: str | Path, *, delimiter: str = ",", encoding: str = "utf-8"
) -> Iterator[dict[str, str]]:
    with Path(path).open(encoding=encoding, newline="") as handle:
        yield from csv.DictReader(handle, delimiter=delimiter)


def read_csv_head(
    path: str | Path, *, limit: int | None, delimiter: str = ",", encoding: str = "utf-8"
) -> list[dict[str, str]]:
    """The first `limit` rows of a CSV file, and no more of the file than they need (ADR-140
    Amendment 12 item 5: a step's sample "reads each source's first ten rows"; the owner's word of
    21 November 2026). The file is closed as soon as the rows are read. `limit=None` is every row,
    as `read_csv` reads them: a run and Test read whole sources.

    A fault in a row past the limit (a byte that is not text in the declared encoding, a malformed
    row) is not met by a read that stops before it. The faults a read does meet are `read_csv`'s:
    the same `OSError`, `UnicodeDecodeError` and `csv.Error`, for the caller to word."""
    if limit is not None and limit < 0:
        raise ValueError("limit must not be negative")
    rows = read_csv(path, delimiter=delimiter, encoding=encoding)
    try:
        return list(rows if limit is None else itertools.islice(rows, limit))
    finally:
        rows.close()  # the generator's `with` closes the file now, not when it is collected
