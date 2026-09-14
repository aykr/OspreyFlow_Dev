"""`revert_load` — `09_INGEST_STUDIO.md` §6: "A load is a unit.
`mantis ingest revert <load_id>` supersedes everything the load created,
leaving the audit trail intact." There is no `mantis` CLI in this build
(`07_BUILD_PLAN.md`'s Phase 2 amendment) — this is that operation as a
plain function, tested directly, with the harness's admin console (Phase
8) as its eventual caller.

Only what the ledger recorded as *this load's own* is touched:
`created_node_ids` (never a node it merely referenced — that node may
belong to other loads too) and `touched_edge_ids` (an edge two loads have
both written to stays live if only one of them is reverted; see
`GraphArcadeDBAdapter.revert_elements` and its conformance tests for what
"touched" actually does to a shared edge). Nothing is deleted — see
`01_DOMAIN_MODEL.md` §2.4's `reverted` note.
"""

from __future__ import annotations

from datetime import datetime

from ports.graph import GraphPort
from schemas.domain import PrincipalId, TxId
from schemas.ingest import LoadRecord


class LoadAlreadyRevertedError(Exception):
    """Raised by `revert_load` on a record that has already been
    reverted — reverting twice is not idempotent-by-design here, since a
    second call with a different `reverted_by` would misattribute the
    action in the audit trail."""


async def revert_load(
    record: LoadRecord,
    *,
    graph: GraphPort,
    tx: TxId,
    reverted_by: PrincipalId,
    now: datetime,
) -> LoadRecord:
    if record.superseded_at is not None:
        raise LoadAlreadyRevertedError(
            f"load {record.load_id!r} was already reverted at {record.superseded_at.isoformat()} "
            f"by {record.superseded_by!r}"
        )
    await graph.revert_elements(record.created_node_ids, record.touched_edge_ids, tx)
    return record.model_copy(update={"superseded_at": now, "superseded_by": reverted_by})
