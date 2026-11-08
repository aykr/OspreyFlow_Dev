"""A dataset's reference list's rows, kept for a run to read (ADR-140 Amendment 12; Q3 (a), the
orchestrator's settlement of 8 November 2026).

A list's record (`schemas.dataset_model.ReferenceList`) is part of the dataset's model; its rows are
loaded data. They are kept at the list's version, at the one place Amendment 11 already names,
`<bucket>/reference_lists/<the list's dataset>/<name>@v<version>.parquet`
(`staging_catalogue.list_rows_path`), written once and never replaced. A run's Lookup reads them
from there (`lists_for_run`), and a list with no rows kept is refused in words: never read as an
empty list, which would leave every Lookup silently unmatched (rule 2).

**Rows reach the file through Studio › Sources** (ADR-140 Amendment 13): a dataset's own list from
one of its own files (`POST /v1/datasets/{id}/reference-lists/{list_id}/import`), a deployment-wide
screening list through its template, each by `services.api.list_connector`. The command line this
module once had, L1.4's stand-in, is retired. `import_list` stays as the tests' seed of a synthetic
list this repository names (rule 9, by the SHA-256 in `synthetic_lists.json`), and nothing else
calls it. A run reads the dataset's own lists and the deployment-wide ones it subscribes to by id
(`subscribed`, from `studio_staging.subscribed_in`).
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Collection, Sequence
from pathlib import Path
from urllib.parse import quote

import pyarrow.fs as pa_fs
import pyarrow.parquet as pq

from schemas.dataset_model import ReferenceList
from schemas.staging import LookupStep, StagingStep

from . import staging as _staging
from .staging import ObjectStorageConfig
from .staging_catalogue import (
    _META,
    StagedTable,
    StagingError,
    list_rows_path,
    read_staged_table,
    readable_lists,
    reference_table,
    stage_sources_and_lists,
)

#: Rule 9: the synthetic lists this module may keep, by the SHA-256 of their bytes.
SYNTHETIC_LISTS = Path(__file__).with_name("synthetic_lists.json")


def _synthetic(path: Path) -> bool:
    """Rule 9: a file is admitted only if its bytes are a synthetic list this repository names in
    `synthetic_lists.json`, as `screening_refresh` admits a synthetic screening list. Judged by
    content, never by where the file sits."""
    digests = json.loads(SYNTHETIC_LISTS.read_text(encoding="utf-8"))["digests"]
    return hashlib.sha256(path.read_bytes()).hexdigest() in digests


def import_list(reference: ReferenceList, csv_path: Path, *, storage: ObjectStorageConfig) -> str:
    """Keep the rows of `csv_path` as `reference`'s rows at its version; returns where. The same
    rows again change nothing; other rows at that version are refused (they are never replaced,
    since elements may name them)."""
    if not _synthetic(csv_path):
        raise StagingError(
            [
                "only a synthetic list this repository names may be imported as a list's rows "
                "(rule 9, synthetic_lists.json); this file is not one"
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


def kept_lists(dataset_id: str, *, storage: ObjectStorageConfig) -> list[ReferenceList]:
    """The lists whose rows are kept for `dataset_id`, each by the record its own file carries, at
    the highest version kept (ADR-140 Amendment 12): no other store of list records exists until
    L1.6. Read from each file's schema alone, never its rows."""
    fs = _staging.filesystem(storage)
    folder = f"{storage.bucket}/reference_lists/{quote(dataset_id, safe='')}"
    if fs.get_file_info(folder).type == pa_fs.FileType.NotFound:
        return []
    newest: dict[str, ReferenceList] = {}
    for info in fs.get_file_info(pa_fs.FileSelector(folder)):
        if info.type != pa_fs.FileType.File or not info.path.endswith(".parquet"):
            continue
        with fs.open_input_file(info.path) as source:
            meta = pq.read_schema(source).metadata or {}
        record = json.loads(meta.get(_META, b"{}")).get("reference")
        if record is None:
            continue
        found = ReferenceList.model_validate(record)
        if found.dataset_id != dataset_id:
            continue
        if found.id not in newest or newest[found.id].version < found.version:
            newest[found.id] = found
    return sorted(newest.values(), key=lambda r: (r.name, r.id))


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
