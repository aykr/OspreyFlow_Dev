"""Metering, part 1 (`06_DECISIONS.md` ADR-110 Amendment 6 point 9, ADR-141 decision 2).

Every run records, on its report and in the ledger (`RunMetering`):

- **wall time**, from the start of the load to its end (`run_recipe_as` times it);
- **rows read**: every row of the file the run read, an incremental refresh's rows below the
  watermark included (they were read, and left);
- **rows staged** and **bytes written to Parquet**: *not measured* (`None`) until phase 7's staging;
- **bytes put to the object store**: what the run gave the media store (`CountingMedia`). The store
  is content-addressed, so a file it already keeps is kept once: the figure is what was put, not
  what the store grew by;
- **graph writes**: every element the run wrote once (`graph_writes`), created, merged into, written
  by the case's rules, withdrawn, or by an extract or enrich stage; a node matched by reference is
  not written.

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


def _load_writes(report: LoadReport) -> int:
    return (
        len(report.created_node_ids)
        + len(report.merged_node_ids)
        + len(report.touched_edge_ids)
        + len(report.rule_node_ids)
        + len(report.rule_created_edge_ids)
        + len(report.rule_merged_edge_ids)
        + len(report.withdrawn_node_ids)
        + len(report.withdrawn_edge_ids)
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
    report: LoadReport | PipelineRunReport, *, wall_seconds: float, object_store_bytes: int
) -> RunMetering:
    return RunMetering(
        wall_ms=round(wall_seconds * 1000),
        rows_read=_rows_read(report),
        object_store_bytes=object_store_bytes,
        graph_writes=graph_writes(report),
    )
