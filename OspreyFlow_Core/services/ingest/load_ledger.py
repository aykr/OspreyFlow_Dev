"""Builds the load ledger entry a completed run of the recipe engine
produces — `01_DOMAIN_MODEL.md` §2.4, ADR-018. Where a `LoadRecord` lives
durably (the same object storage as the Parquet staging layer)
is not decided here; this module only shapes
the record `load_revert.py` needs, from the `LoadReport`
`engine.run_recipe` already returns.
"""

from __future__ import annotations

from datetime import datetime

from schemas.domain import PrincipalId
from schemas.ingest import LoadRecord, LoadReport


def load_record_from_report(
    report: LoadReport,
    *,
    source: str,
    created_by: PrincipalId,
    started_at: datetime,
    now: datetime,
    investigation_id: str | None = None,
    released_from: str | None = None,
) -> LoadRecord:
    """Every load from ADR-127 decision 6 on stamps its events with its `load_id`, so a record made
    here says so (`events_stamped`); a record from before has no such key and reads as false."""
    return LoadRecord(
        load_id=report.load_id,
        recipe_id=report.recipe_id,
        recipe_version=report.recipe_version,
        source=source,
        started_at=started_at,
        completed_at=now,
        created_by=created_by,
        created_node_ids=[*report.created_node_ids, *report.rule_node_ids],
        touched_edge_ids=[
            *report.touched_edge_ids,
            *report.rule_created_edge_ids,
            *report.rule_merged_edge_ids,
        ],
        rejected_count=len(report.rejections),
        investigation_id=investigation_id,
        created_edge_ids=[*report.created_edge_ids, *report.rule_created_edge_ids],
        merged_edge_ids=[*report.merged_edge_ids, *report.rule_merged_edge_ids],
        merged_node_ids=report.merged_node_ids,
        released_from=released_from,
        events_stamped=True,
    )
