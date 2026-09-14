"""Builds the load ledger entry a completed run of the recipe engine
produces — `01_DOMAIN_MODEL.md` §2.4, ADR-018. Where a `LoadRecord` lives
durably (the same object storage as the Parquet staging layer,
`07_BUILD_PLAN.md` Phase 2) is not decided here; this module only shapes
the record `revert_load` (`revert.py`) needs, from the `LoadReport`
`engine.run_recipe` already returns.
"""

from __future__ import annotations

from datetime import datetime

from schemas.domain import PrincipalId
from schemas.ingest import LoadRecord, LoadReport


def load_record_from_report(
    report: LoadReport, *, source: str, created_by: PrincipalId, started_at: datetime, now: datetime
) -> LoadRecord:
    return LoadRecord(
        load_id=report.load_id,
        recipe_id=report.recipe_id,
        recipe_version=report.recipe_version,
        source=source,
        started_at=started_at,
        completed_at=now,
        created_by=created_by,
        created_node_ids=report.created_node_ids,
        touched_edge_ids=report.touched_edge_ids,
        rejected_count=len(report.rejections),
    )
