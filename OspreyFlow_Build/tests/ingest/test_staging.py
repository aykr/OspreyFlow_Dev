"""Parquet staging round trip — `03_CONDUIT_MIDDLEWARE.md` §5.1. Against a
live MinIO instance, not a mock: the property under test is specifically
"the data that comes back out of object storage is the data that went in,"
which a mock cannot prove.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.ingest.staging import (
    ObjectStorageConfig,
    RawStagedRow,
    StagedEdge,
    StagedEntity,
    StagedRow,
    read_raw_rows,
    read_staged_rows,
    stage_raw_rows,
    stage_rows,
)


def _storage() -> ObjectStorageConfig:
    return ObjectStorageConfig.from_env()


async def test_staged_rows_round_trip_through_object_storage_unchanged() -> None:
    rows = [
        StagedRow(
            load_id="load-staging-test-1",
            recipe_id="cdr-fixture",
            recipe_version=4,
            source="carrier-a.csv",
            row_index=0,
            duplicate_row_indices=[1, 2],
            entities=[
                StagedEntity(
                    ref="a", type="Endpoint", properties={"value_normalised": "+441621926368"}
                ),
                StagedEntity(
                    ref="b", type="Endpoint", properties={"value_normalised": "+447911123456"}
                ),
            ],
            edges=[
                StagedEdge(
                    type="COMMUNICATED_WITH",
                    from_ref="a",
                    to_ref="b",
                    properties={"duration_s": 60, "direction": "outbound"},
                    instant=datetime(2026, 1, 10, 10, 0, tzinfo=UTC),
                )
            ],
        ),
        StagedRow(
            load_id="load-staging-test-1",
            recipe_id="cdr-fixture",
            recipe_version=4,
            source="carrier-a.csv",
            row_index=3,
            duplicate_row_indices=[],
            entities=[
                StagedEntity(
                    ref="a", type="Endpoint", properties={"value_normalised": "+441621926368"}
                )
            ],
            edges=[],
        ),
    ]
    storage = _storage()
    path = stage_rows(rows, storage=storage, load_id="load-staging-test-1")
    loaded = read_staged_rows(path, storage=storage)

    assert loaded == rows


async def test_staged_row_with_no_temporal_edge_round_trips_instant_as_none() -> None:
    rows = [
        StagedRow(
            load_id="load-staging-test-2",
            recipe_id="cdr-fixture",
            recipe_version=4,
            source="carrier-a.csv",
            row_index=0,
            entities=[StagedEntity(ref="a", type="Endpoint", properties={})],
            edges=[
                StagedEdge(
                    type="ASSOCIATE_OF", from_ref="a", to_ref="a", properties={}, instant=None
                )
            ],
        )
    ]
    storage = _storage()
    path = stage_rows(rows, storage=storage, load_id="load-staging-test-2")
    loaded = read_staged_rows(path, storage=storage)

    assert loaded[0].edges[0].instant is None


async def test_raw_rows_round_trip_exactly_as_the_connector_produced_them() -> None:
    """`03_CONDUIT_MIDDLEWARE.md` §5.1: `stage(raw)` captures every field
    exactly as it appeared, before any transform — no resolution, no
    dedup, no dropped rows."""
    rows = [
        {"seq": "1", "a_party": "01621926368", "b_party": "07911123456", "start_time": "junk"},
        {"seq": "2", "a_party": "01621926368", "b_party": "07911123456", "start_time": "junk"},
    ]
    storage = _storage()
    path = stage_raw_rows(rows, storage=storage, load_id="load-raw-test-1", source="cdr.csv")
    loaded = read_raw_rows(path, storage=storage)

    assert loaded == [
        RawStagedRow(load_id="load-raw-test-1", source="cdr.csv", row_index=0, fields=rows[0]),
        RawStagedRow(load_id="load-raw-test-1", source="cdr.csv", row_index=1, fields=rows[1]),
    ]


async def test_raw_staging_keeps_a_row_a_later_normalisation_step_would_reject() -> None:
    """The raw dataset is written before normalisation runs, so a row that
    `resolve_rows` would later reject (an unparseable `start_time`) still
    lands here — that is the entire point: recovery does not depend on
    what the *original* recipe accepted."""
    rows = [{"start_time": "not-a-real-timestamp"}]
    storage = _storage()
    path = stage_raw_rows(rows, storage=storage, load_id="load-raw-test-2", source="cdr.csv")
    loaded = read_raw_rows(path, storage=storage)

    assert loaded[0].fields == {"start_time": "not-a-real-timestamp"}


async def test_staged_row_with_no_entities_or_edges_round_trips_as_empty(
) -> None:
    """A row every element of which was conditionally absent this row
    (`when` did not hold) still needs to round-trip — an empty row is not
    the same as no row, since `row_index`/`duplicate_row_indices` still
    matter for provenance."""
    rows = [
        StagedRow(
            load_id="load-staging-test-3",
            recipe_id="cdr-fixture",
            recipe_version=4,
            source="carrier-a.csv",
            row_index=5,
            duplicate_row_indices=[6],
        )
    ]
    storage = _storage()
    path = stage_rows(rows, storage=storage, load_id="load-staging-test-3")
    loaded = read_staged_rows(path, storage=storage)

    assert loaded == rows
    assert loaded[0].entities == []
    assert loaded[0].edges == []
