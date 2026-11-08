"""A dataset's reference list's rows, kept for a run to read (ADR-140 Amendment 12; Q3 (a), the
orchestrator's settlement of 8 November 2026).

A list's record (`schemas.dataset_model.ReferenceList`) is part of the dataset's model; its rows are
loaded data. They are kept at the list's version, at the one place Amendment 11 already names,
`<bucket>/reference_lists/<the list's dataset>/<name>@v<version>.parquet`
(`staging_catalogue.list_rows_path`), written once and never replaced. A run's Lookup reads them
from there (`lists_for_run`), and a list with no rows kept is refused in words: never read as an
empty list, which would leave every Lookup silently unmatched (rule 2).

Until L1.6 builds import in the Studio, rows are put there by this module, from a **synthetic
fixture in this repository's tests only** (rule 9):

    python -m services.ingest.reference_list_import --dataset pid --list-id rl-est \\
        --name establishments --key estab_id --version 3 --bucket staging \\
        ../OspreyFlow_Build/tests/ingest/fixtures/visits_and_contacts/establishments.csv

A screening list is deployment-wide, and no dataset can subscribe to one until L1.6, so a run reads
only the dataset's own lists for now; the save gate already refuses a Lookup of any other.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import sys
from collections.abc import Collection, Sequence
from pathlib import Path

import pyarrow.fs as pa_fs

from schemas.dataset_model import ReferenceList
from schemas.staging import LookupStep, StagingStep

from . import staging as _staging
from .staging import ObjectStorageConfig
from .staging_catalogue import (
    StagedTable,
    StagingError,
    list_rows_path,
    read_staged_table,
    readable_lists,
    reference_table,
    stage_sources_and_lists,
)

#: Rule 9: the only files this module reads are the repository's own synthetic test fixtures.
_REPOSITORY = Path(__file__).resolve().parents[3]
_FIXTURES_UNDER = _REPOSITORY / "OspreyFlow_Build" / "tests"


def _synthetic(path: Path) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(_FIXTURES_UNDER) and "fixtures" in resolved.parts


def import_list(reference: ReferenceList, csv_path: Path, *, storage: ObjectStorageConfig) -> str:
    """Keep the rows of `csv_path` as `reference`'s rows at its version; returns where. The same
    rows again change nothing; other rows at that version are refused (they are never replaced,
    since elements may name them)."""
    if not _synthetic(csv_path):
        raise StagingError(
            [
                "only a synthetic fixture in this repository's tests may be imported as a list's "
                "rows (rule 9); this file is not one"
            ]
        )
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    table = reference_table(reference, rows)
    stage_sources_and_lists({}, {reference.name: table}, storage=storage)
    return list_rows_path(reference, storage=storage)


def read_list_rows(reference: ReferenceList, *, storage: ObjectStorageConfig) -> StagedTable:
    """`reference`'s rows at its version, as a run's Lookup reads them. No file, or a file holding
    another list's rows, is refused in words."""
    path = list_rows_path(reference, storage=storage)
    fs = _staging.filesystem(storage)
    if fs.get_file_info(path).type == pa_fs.FileType.NotFound:
        raise StagingError(
            [
                f"the list {reference.name!r} (version {reference.version}) has no rows kept for "
                "a run to read: import its rows first; nothing was loaded"
            ]
        )
    table = read_staged_table(path, storage=storage)
    if table.reference != reference:
        raise StagingError(
            [
                f"the rows kept for the list {reference.name!r} (version {reference.version}) are "
                "another list's; nothing was loaded"
            ]
        )
    return table


def lists_for_run(
    steps: Sequence[StagingStep],
    references: Collection[ReferenceList],
    *,
    dataset_id: str,
    storage: ObjectStorageConfig,
    subscribed: Collection[str] = (),
) -> dict[str, StagedTable]:
    """The lists a run's Lookups read, by name: each one the dataset may read (`readable_lists`),
    read from its version's file. A Lookup of a list it may not read is refused in the save gate's
    own words, before any file is opened."""
    readable, _clashes = readable_lists(references, dataset_id=dataset_id, subscribed=subscribed)
    wanted = [s for s in steps if isinstance(s, LookupStep)]
    missing = [
        f"step {s.id!r} looks up {s.list_!r}, which names no list this dataset holds or "
        "subscribes to"
        for s in wanted
        if s.list_ not in readable
    ]
    if missing:
        raise StagingError(missing)
    return {s.list_: read_list_rows(readable[s.list_], storage=storage) for s in wanted}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--list-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--key", required=True, help="the list's key column")
    parser.add_argument("--version", required=True, type=int)
    parser.add_argument("--kind", default="reference")
    parser.add_argument("--bucket", default=None, help="the object store's bucket (else env)")
    parser.add_argument("csv", type=Path)
    args = parser.parse_args(argv)
    reference = ReferenceList(
        id=args.list_id,
        dataset_id=args.dataset,
        name=args.name,
        kind=args.kind,
        key_column=args.key,
        version=args.version,
    )
    storage = ObjectStorageConfig.from_env()
    if args.bucket:
        storage = dataclasses.replace(storage, bucket=args.bucket)
    try:
        path = import_list(reference, args.csv, storage=storage)
    except StagingError as refused:
        print("\n".join(refused.problems), file=sys.stderr)
        return 1
    print(f"kept {args.name}@v{args.version} at {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
