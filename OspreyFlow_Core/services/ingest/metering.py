"""Metering, part 1 (`06_DECISIONS.md` ADR-110 Amendment 6 point 9, ADR-141 decision 2).

Every run records, on its report and in the ledger (`RunMetering`):

- **wall time**, from the start of the load to its end (`run_recipe_as` times it);
- **rows read**: every row of the file the run read, an incremental refresh's rows below the
  watermark included (they were read, and left);
- **rows staged** and **bytes written to Parquet**: a staged run's, every step's table's rows and
  the bytes of their Parquet (`StagingMeter`; ADR-140 Amendment 12); *not measured* (`None`) for
  any other run;
- **bytes put to the object store**: what the run gave the media store (`CountingMedia`). The store
  is content-addressed, so a file it already keeps is kept once: the figure is what was put, not
  what the store grew by;
- **graph writes**: every element the run wrote once (`graph_writes`), created, merged into, written
  by the case's rules, or by an extract or enrich stage; a node matched by reference is not written.
  A full snapshot's withdrawal writes no element (ADR-110 Amendment 15: it takes back the dropped
  rows' own events alone), so it is never counted here.

A figure is never 0 for "not measured" (rule 2).
"""

from __future__ import annotations

from ports.media import MediaStore
from schemas.ingest import LoadReport, PipelineRunReport, RunMetering


class CountingMedia:
    """A `MediaStore` that counts the bytes it is given, and passes everything on."""

    def __init__(self, inner: MediaStore) -> None:
        self._inner = inner
        self.bytes_written = 0

    async def put(self, data: bytes, content_type: str) -> str:
        self.bytes_written += len(data)
        return await self._inner.put(data, content_type)

    async def get(self, ref: str) -> bytes:
        return await self._inner.get(ref)


class StagingMeter:
    """What a staged run's steps wrote to Parquet (ADR-140 Amendment 12): handed down the run as
    `CountingMedia` is, and read once it ends. `None` until a staged load adds to it."""

    def __init__(self) -> None:
        self.rows_staged: int | None = None
        self.parquet_bytes: int | None = None

    def add(self, rows_staged: int, parquet_bytes: int) -> None:
        self.rows_staged = (self.rows_staged or 0) + rows_staged
        self.parquet_bytes = (self.parquet_bytes or 0) + parquet_bytes


def _load_writes(report: LoadReport) -> int:
    # A full snapshot's withdrawal writes no element (ADR-110 Amendment 15), so nothing of it is
    # counted; the run says what it withdrew in `rows_withdrawn` and its notes.
    return (
        len(report.created_node_ids)
        + len(report.merged_node_ids)
        + len(report.touched_edge_ids)
        + len(report.rule_node_ids)
        + len(report.rule_created_edge_ids)
        + len(report.rule_merged_edge_ids)
    )


def graph_writes(report: LoadReport | PipelineRunReport) -> int:
    if isinstance(report, LoadReport):
        return _load_writes(report)
    return (
        sum(_load_writes(b.report) for b in report.branches)
        + sum(x.nodes_written_inferred for x in report.extracts)
        + sum(e.matched_local + e.matched_online for e in report.enriches)
    )


def _rows_read(report: LoadReport | PipelineRunReport) -> int:
    if isinstance(report, LoadReport):
        return report.rows_read + report.rows_below_watermark
    return report.rows_read + sum(b.report.rows_below_watermark for b in report.branches)


def metering_of(
    report: LoadReport | PipelineRunReport,
    *,
    wall_seconds: float,
    object_store_bytes: int,
    staging: StagingMeter | None = None,
) -> RunMetering:
    return RunMetering(
        wall_ms=round(wall_seconds * 1000),
        rows_read=_rows_read(report),
        rows_staged=staging.rows_staged if staging is not None else None,
        parquet_bytes=staging.parquet_bytes if staging is not None else None,
        object_store_bytes=object_store_bytes,
        graph_writes=graph_writes(report),
    )
