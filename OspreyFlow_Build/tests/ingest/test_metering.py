"""Metering, part 1 (ADR-110 Amendment 6 point 9, ADR-141 decision 2): every run records its wall
time, rows read and staged, bytes written to Parquet and to the object store, and graph writes, on
the report and in the ledger; a figure the run cannot yet measure is *not measured* (`None`), never
0. `services/ingest/metering` counts; `run_recipe_as` stamps.

What a mistake would do, and the case that catches it:

- a write left out of the count, or one counted twice
  (`test_a_loads_graph_writes_are_every_element_it_wrote_once`);
- a pipeline's stages left out (`test_a_pipelines_graph_writes_add_its_branches_and_stages`);
- an incremental refresh's rows below the watermark left out of the rows read
  (`test_the_rows_read_are_every_row_of_the_file`);
- a figure not yet measured shown as 0 (`test_what_is_not_yet_measured_is_none`);
- the object store's bytes not counted, or the run's figures lost on the way to the ledger
  (`tests/services/api/test_run_metering_ledger.py`)."""

from __future__ import annotations

from services.ingest.metering import CountingMedia, graph_writes, metering_of

from adapters.media_objectstore.testing import InMemoryMediaStore
from schemas.ingest import (
    BranchRunReport,
    EnrichStageReport,
    ExtractStageReport,
    LoadReport,
    PipelineRunReport,
)


def _load(**lists: object) -> LoadReport:
    return LoadReport(load_id="l", recipe_id="r", recipe_version=1, **lists)  # type: ignore[arg-type]


def test_a_loads_graph_writes_are_every_element_it_wrote_once() -> None:
    report = _load(
        created_node_ids=["n1", "n2"], merged_node_ids=["d1"],
        touched_edge_ids=["e1", "e2"], created_edge_ids=["e1"], merged_edge_ids=["e2"],
        rule_node_ids=["a1"], rule_created_edge_ids=["ae1"], rule_merged_edge_ids=["ae2"],
        withdrawn_node_ids=["w1"], withdrawn_edge_ids=["we1"],
        referenced_node_ids=["ref1"],
    )  # fmt: skip
    # created and merged edges are within touched: counted once; a referenced node is not written.
    assert graph_writes(report) == 2 + 1 + 2 + 1 + 2 + 2


def test_a_pipelines_graph_writes_add_its_branches_and_stages() -> None:
    branch = BranchRunReport(source_id="s", source_label="S", report=_load(created_node_ids=["n1"]))
    report = PipelineRunReport(
        load_id="l", recipe_id="r", recipe_version=1, branches=[branch, branch],
        extracts=[
            ExtractStageReport(node_id="x", library="l", output="o", nodes_written_inferred=3)
        ],
        enriches=[
            EnrichStageReport(node_id="g", geocoder="local", matched_local=2, matched_online=1)
        ],
    )  # fmt: skip
    assert graph_writes(report) == 1 + 1 + 3 + 2 + 1


def test_the_rows_read_are_every_row_of_the_file() -> None:
    report = _load(rows_read=2, rows_below_watermark=5)
    assert metering_of(report, wall_seconds=1.5, object_store_bytes=0).rows_read == 7
    branch = BranchRunReport(source_id="s", source_label="S", report=report)
    pipeline = PipelineRunReport(
        load_id="l", recipe_id="r", recipe_version=1, branches=[branch], rows_read=2
    )
    assert metering_of(pipeline, wall_seconds=1.5, object_store_bytes=0).rows_read == 7


def test_what_is_not_yet_measured_is_none() -> None:
    metering = metering_of(_load(), wall_seconds=0.25, object_store_bytes=12)
    assert (metering.rows_staged, metering.parquet_bytes) == (None, None), "phase 7's staging"
    assert (metering.wall_ms, metering.object_store_bytes, metering.graph_writes) == (250, 12, 0)


async def test_the_counting_media_store_counts_what_it_is_given_and_passes_it_on() -> None:
    inner = InMemoryMediaStore()
    media = CountingMedia(inner)
    ref = await media.put(b"0123456789", "text/plain")
    await media.put(b"abc", "text/plain")
    assert media.bytes_written == 13
    assert await inner.get(ref) == b"0123456789"
    assert await media.get(ref) == b"0123456789", "a read is not a write"
    assert media.bytes_written == 13


def test_a_route_shows_a_runs_metering_only_to_a_reader_who_may_see_its_counts() -> None:
    """Rules 3 and 4: the figures count the run's rows and writes, so they go with the counts."""
    from services.api.load_records import report_view

    from schemas.domain import Handling, Principal
    from tests.ingest.test_row_keys import SCHEME

    secret = Handling(
        classification="SECRET", handling_code="P", owning_unit="unit-1", originator="unit-1"
    )
    report = _load(rows_read=4, markings=[secret])
    report.metering = metering_of(report, wall_seconds=2, object_store_bytes=9)
    branch = BranchRunReport(source_id="s", source_label="S", report=report)
    pipeline = PipelineRunReport(
        load_id="l", recipe_id="r", recipe_version=1, branches=[branch], markings=[secret],
        metering=report.metering,
    )  # fmt: skip
    cleared = Principal(id="a", clearance="SECRET", org_unit="unit-1")
    below = Principal(id="b", clearance="OFFICIAL", org_unit="unit-1")
    for shown in (report_view(report, cleared, SCHEME), report_view(pipeline, cleared, SCHEME)):
        assert shown.metering == report.metering
    for withheld in (report_view(report, below, SCHEME), report_view(pipeline, below, SCHEME)):
        assert withheld.withheld and withheld.metering is None
