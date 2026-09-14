"""Parquet staging — `03_CONDUIT_MIDDLEWARE.md` §5.1: two staging
datasets, not one, and the order matters.

**`stage_raw_rows`/`RawStagedRow`** land the source rows in Parquet
*before* any transform touches them — every field exactly as the
connector produced it, typed as text, immutable, written right after
`identify` and before `normalise`. This is what actually makes
"re-extraction, re-resolution and schema migration possible without
re-uploading" true: a normaliser bug found in month six is correctable
for every field, not only the ones a recipe happened to also bind as
`value_raw`, and an ontology version that wants a property the original
recipe never captured has somewhere to read it from. Staging only the
post-transform rows — this module's original Phase 2 shape — did neither;
that was a real defect, not a design choice, and it is why raw staging
exists as its own step rather than being folded into the normalised one.

**`stage_rows`/`StagedRow`** land the resolved, deduplicated rows in a
second Parquet dataset, carrying the raw row's `row_index` so the two
datasets join. This is what `run_recipe` actually reads back for the load
step — `stage_rows` writes to object storage and `run_recipe` reads the
just-written file back before the first `GraphPort` write, so that round
trip is genuinely load-bearing, not cosmetic. The raw dataset is not
re-read within the same run; it exists for a *later* run (a corrected
recipe, a new ontology version) to read from instead of asking for the
source file again.

Object storage is MinIO (`docs/07_BUILD_PLAN.md` Phase 2), reached through
`pyarrow.fs.S3FileSystem` — MinIO is S3-protocol-compatible, so no separate
client library is needed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import pyarrow as pa
import pyarrow.fs as pa_fs
import pyarrow.parquet as pq


@dataclass(frozen=True)
class ObjectStorageConfig:
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "mantisnexus-staging"
    use_ssl: bool = False

    @classmethod
    def from_env(cls) -> ObjectStorageConfig:
        """CI and local `docker run` both read connection info from the
        environment — the same pattern `ArcadeDBConfig.from_env` uses."""
        return cls(
            endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
            bucket=os.environ.get("MINIO_BUCKET", "mantisnexus-staging"),
            use_ssl=os.environ.get("MINIO_USE_SSL", "false").lower() == "true",
        )


def filesystem(config: ObjectStorageConfig) -> pa_fs.S3FileSystem:
    return pa_fs.S3FileSystem(
        endpoint_override=config.endpoint,
        access_key=config.access_key,
        secret_key=config.secret_key,
        scheme="https" if config.use_ssl else "http",
        # The staging bucket is provisioned once per deployment (or once
        # per test database, here) — allowed so a fresh MinIO/test run
        # doesn't need a separate provisioning step.
        allow_bucket_creation=True,
    )


# --- stage(raw) — 03_CONDUIT_MIDDLEWARE.md §5.1, before normalise -------


@dataclass(frozen=True)
class RawStagedRow:
    """One source row exactly as the connector produced it — every field
    as text, nothing transformed, nothing dropped. `row_index` is the
    join key `StagedRow` carries forward into the normalised dataset."""

    load_id: str
    source: str
    row_index: int
    fields: dict[str, str]


def _raw_rows_to_table(rows: Sequence[Mapping[str, str]], *, load_id: str, source: str) -> pa.Table:
    return pa.table(
        {
            "load_id": [load_id] * len(rows),
            "source": [source] * len(rows),
            "row_index": list(range(len(rows))),
            "fields_json": [json.dumps(dict(row)) for row in rows],
        }
    )


def stage_raw_rows(
    rows: Sequence[Mapping[str, str]], *, storage: ObjectStorageConfig, load_id: str, source: str
) -> str:
    """Writes every row of `rows` — unfiltered, undeduplicated,
    untransformed — to `<bucket>/loads/<load_id>/raw.parquet` and returns
    the path written."""
    path = f"{storage.bucket}/loads/{load_id}/raw.parquet"
    fs = filesystem(storage)
    fs.create_dir(storage.bucket)
    table = _raw_rows_to_table(rows, load_id=load_id, source=source)
    with fs.open_output_stream(path) as sink:
        pq.write_table(table, sink)
    return path


def read_raw_rows(path: str, *, storage: ObjectStorageConfig) -> list[RawStagedRow]:
    fs = filesystem(storage)
    with fs.open_input_file(path) as source:
        table = pq.read_table(source)
    return [
        RawStagedRow(
            load_id=record["load_id"],
            source=record["source"],
            row_index=record["row_index"],
            fields=json.loads(record["fields_json"]),
        )
        for record in table.to_pylist()
    ]


# --- stage(normalised) — after normalise/deduplicate --------------------


@dataclass(frozen=True)
class StagedEntity:
    ref: str
    type: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class StagedEdge:
    type: str
    from_ref: str
    to_ref: str
    properties: dict[str, Any]
    instant: datetime | None = None


@dataclass(frozen=True)
class StagedRow:
    """One surviving (post-dedup) source row, fully resolved. `row_index`
    and `duplicate_row_indices` are what let the load step attribute
    provenance back to every original row a duplicate group collapsed
    (`01_DOMAIN_MODEL.md` §7 rule 2), and what join this dataset back to
    `stage_raw_rows`'s — the same `row_index` values, into the same
    `load_id`."""

    load_id: str
    recipe_id: str
    recipe_version: int
    source: str
    row_index: int
    duplicate_row_indices: list[int] = field(default_factory=list)
    entities: list[StagedEntity] = field(default_factory=list)
    edges: list[StagedEdge] = field(default_factory=list)


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"not JSON-serialisable in a staged property: {value!r}")


def _rows_to_table(rows: Sequence[StagedRow]) -> pa.Table:
    return pa.table(
        {
            "load_id": [r.load_id for r in rows],
            "recipe_id": [r.recipe_id for r in rows],
            "recipe_version": [r.recipe_version for r in rows],
            "source": [r.source for r in rows],
            "row_index": [r.row_index for r in rows],
            "duplicate_row_indices": [json.dumps(r.duplicate_row_indices) for r in rows],
            "entities_json": [
                json.dumps([asdict(e) for e in r.entities], default=_json_default) for r in rows
            ],
            "edges_json": [
                json.dumps(
                    [
                        {**asdict(e), "instant": e.instant.isoformat() if e.instant else None}
                        for e in r.edges
                    ]
                )
                for r in rows
            ],
        }
    )


def stage_rows(rows: Sequence[StagedRow], *, storage: ObjectStorageConfig, load_id: str) -> str:
    """Writes `rows` to `<bucket>/loads/<load_id>/normalised.parquet` and
    returns the path written (bucket-relative), for `read_staged_rows` or
    a later re-run to read back."""
    path = f"{storage.bucket}/loads/{load_id}/normalised.parquet"
    fs = filesystem(storage)
    fs.create_dir(storage.bucket)
    table = _rows_to_table(rows)
    with fs.open_output_stream(path) as sink:
        pq.write_table(table, sink)
    return path


def read_staged_rows(path: str, *, storage: ObjectStorageConfig) -> list[StagedRow]:
    fs = filesystem(storage)
    with fs.open_input_file(path) as source:
        table = pq.read_table(source)

    rows: list[StagedRow] = []
    for record in table.to_pylist():
        entities = [
            StagedEntity(ref=e["ref"], type=e["type"], properties=e["properties"])
            for e in json.loads(record["entities_json"])
        ]
        edges = [
            StagedEdge(
                type=e["type"],
                from_ref=e["from_ref"],
                to_ref=e["to_ref"],
                properties=e["properties"],
                instant=datetime.fromisoformat(e["instant"]).astimezone(UTC)
                if e["instant"]
                else None,
            )
            for e in json.loads(record["edges_json"])
        ]
        rows.append(
            StagedRow(
                load_id=record["load_id"],
                recipe_id=record["recipe_id"],
                recipe_version=record["recipe_version"],
                source=record["source"],
                row_index=record["row_index"],
                duplicate_row_indices=json.loads(record["duplicate_row_indices"]),
                entities=entities,
                edges=edges,
            )
        )
    return rows
