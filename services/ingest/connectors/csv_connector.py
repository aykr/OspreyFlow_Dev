"""Generic CSV connector — `07_BUILD_PLAN.md` Phase 2's "CSV, JSON and
generic delimited" bullet, scoped here to CSV. Every connector yields the
same `Iterable[Mapping[str, str]]` row shape the engine consumes, so a
second format is an additional connector module, not a change to
`services/ingest/engine.py`.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path


def read_csv(
    path: str | Path, *, delimiter: str = ",", encoding: str = "utf-8"
) -> Iterator[dict[str, str]]:
    with Path(path).open(encoding=encoding, newline="") as handle:
        yield from csv.DictReader(handle, delimiter=delimiter)
