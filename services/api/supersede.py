"""The job-based path for `GraphPort.supersede_node` above a degree
threshold — `docs/07_BUILD_PLAN.md` Phase 3: "measured (not assumed) at
~41 seconds for a 5,000-degree node against a local ArcadeDB instance...
a request that takes 41 seconds is not a reasonable synchronous operation
... Same job/status-id shape as `PatternQuery`'s 'large results return a
job id' (`03_CONDUIT_MIDDLEWARE.md` §3.3)."

**Why this is a routing decision with no worker attached yet.** Every
named caller of `supersede_node` — Phase 6's retraction, Phase 8's
judgement-review loop (`packages/ports/graph.py`'s own docstring) — lands
in a later phase, and correspondingly there is no analyst-facing route in
`03_CONDUIT_MIDDLEWARE.md` §3 that calls `supersede_node` yet either. What
Phase 3 owns is the primitive those callers will use: measure the node's
degree, and either run the correction inline or hand it to the job queue,
never leaving the choice to whoever writes the eventual caller. A worker
process that drains `jobs:supersede_node` and actually calls
`GraphPort.supersede_node` in the background is not written here, for the
same reason `find_node` landed on the port ahead of a caller in Phase 2
(`00_ARCHITECTURE.md` §2.1) — the capability is correct and tested now;
the consumer is written against a real caller, not a placeholder one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ports.graph import GraphPort
from schemas.domain import NodeId, NodeWrite, Principal, TxId

from .jobs import JobQueue

#: `01_DOMAIN_MODEL.md` §8.2's measured figure — ~41s at 5,000 degree —
#: informs the *shape* of this default (well under the point synchronous
#: stops being reasonable), not the exact number: `config.
#: DEFAULT_SUPERSEDE_JOB_DEGREE_THRESHOLD` is what a deployment actually
#: tunes.
JOB_TYPE_SUPERSEDE_NODE = "supersede_node"


class SupersedeNodeAccepted(BaseModel):
    """What a caller gets back either way — `mode` tells it whether
    `result_node_id` is already final or whether to poll
    `GET /v1/jobs/{job_id}/events` (`03_CONDUIT_MIDDLEWARE.md` §3.3)."""

    mode: Literal["sync", "job"]
    result_node_id: NodeId | None = None
    job_id: str | None = None


async def submit_supersede_node(
    node_id: NodeId,
    replacement: NodeWrite,
    tx: TxId,
    *,
    graph: GraphPort,
    principal: Principal,
    jobs: JobQueue,
    degree_threshold: int,
) -> SupersedeNodeAccepted:
    stats = await graph.neighbourhood_stats(node_id, principal)
    if stats.degree < degree_threshold:
        new_id = await graph.supersede_node(node_id, replacement, tx)
        return SupersedeNodeAccepted(mode="sync", result_node_id=new_id)

    job_id = await jobs.submit(
        JOB_TYPE_SUPERSEDE_NODE,
        {
            "node_id": node_id,
            "replacement": replacement.model_dump(mode="json"),
            "degree_at_submission": stats.degree,
            "submitted_by": principal.id,
        },
    )
    return SupersedeNodeAccepted(mode="job", job_id=job_id)


async def run_supersede_node_job(
    payload: dict[str, object], *, graph: GraphPort, tx: TxId
) -> dict[str, object]:
    """The background half a worker process calls — `services/api/worker.py`'s `JobWorker`, now
    that one exists (`06_DECISIONS.md` ADR-025). Separated from `submit_supersede_node` so that
    worker tests against this function rather than reconstructing the payload shape by hand.
    Returns a `dict`, not a bare `NodeId`, to match `JobWorker`'s one fixed handler shape
    (`JobRecord.result: dict[str, Any] | None`) — the same contract `run_resolve_entity_type_job`
    presents alongside it."""
    node_id = str(payload["node_id"])
    replacement = NodeWrite.model_validate(payload["replacement"])
    new_id = await graph.supersede_node(node_id, replacement, tx)
    return {"result_node_id": new_id}


__all__ = [
    "JOB_TYPE_SUPERSEDE_NODE",
    "SupersedeNodeAccepted",
    "run_supersede_node_job",
    "submit_supersede_node",
]
