"""`POST /v1/investigations/{investigation_id}/compute/{metric}` — `ComputePort`'s first real
caller, Phase 7 Stage 3. Closes the composed caller-contract test `packages/schemas/compute.py`'s
own docstring disclosed as owed: "that composed claim is owed by whichever stage builds
`ComputePort`'s first real caller."

Nested under `/v1/investigations/{investigation_id}/...`, not a bare `/v1/compute/{metric}` —
the same departure `resolution.py` already took for τ/manual-link/explain ("a real shape belongs
in code, not only in a docstring"): a metric is computed over one investigation's own working set,
the same shape as every other working-set read already nested this way. `{metric}` spans the eight
named panel metrics (`ComputeMetricName` below) — `temporal_motifs` and `shortest_paths` are
excluded, per `adapters/compute_rustworkx`'s own disclosed `NotImplementedError`s: neither has a
claiming caller yet.

**The defect found while designing this, and its fix.** `WorkingSetService.current_membership`
is **deliberately unfiltered** — its own docstring: "the full source-fidelity... membership...
`restore` re-projects fresh against whoever is restoring." Feeding it straight to `ComputePort`
would let a hidden node's own existence leak through a visible node's own degree or centrality
score — exactly `CLAUDE.md` rule 3's concern, and the same shape of defect already found and fixed
for `set_resolution_threshold`/`explain_cluster` (the third and fourth instances of the same
repeated pattern). `narrow_to_visible` (`services/api/access.py`) is the same narrowing
function those two, and the Dossier, already use — this is disclosed as its fourth caller, not a
fifth independent copy of the pattern. Proven by
`tests/services/api/working_set/test_compute_access_control.py`.

**A second, distinct gap found while building this caller, in `narrow_to_visible` itself, per
standing rule 12's own naming discipline — not the same property as the paragraph above.**
`GraphPort.expand`'s own `depth=1` traversal can return an edge to a neighbour that is fully
*visible* to the principal but was never part of the *requested* node set — no classification
violation at all, since `expand` has no reason to exclude a visible node from anything. Before the
fix, `narrow_to_visible`'s own node filter correctly dropped that neighbour from
`VisibilityResult.nodes`, but `VisibilityResult.edges` still carried the edge naming it verbatim —
a result whose own edges could reference a node absent from its own nodes. Fixed directly in
`services/api/access.py`, proven by `tests/services/api/test_access.py` — a different test from
the one above, because `expand` itself already handles the hidden-classification case before
`narrow_to_visible` ever runs, so a fixture built around a hidden node cannot exercise this
specific gap (checked directly, not assumed: the composed test above still passes with this
second fix reverted).

**The sync/job split, at the budget's own stated boundary, not an invented number.**
`02_GLASS_FRONTEND.md` §5: "Metric recompute on filter change: < 500 ms for ≤ 20k, otherwise
progressive with a visible indicator" — `SYNC_NODE_LIMIT` below is that figure, mirroring
`submit_supersede_node`'s own degree-threshold sync/job split rather than a fresh threshold
decision.

**A real gap this route does not close, disclosed rather than silently accepted.**
`02_GLASS_FRONTEND.md` line 206 ("Betweenness (exact to 20k nodes, Brandes-sampled above)") implies
betweenness should switch to an approximation above the same 20k boundary this route uses for its
sync/job split — but neither `CentralityRequest` (Stage 2) nor `adapters/compute_rustworkx`'s own
`centrality` method (Stage 3) carries a sampling parameter or branch at all; the job-mode path
below runs the identical exact `rustworkx.betweenness_centrality` call regardless of population
size — real algorithmic work, disclosed as its own gap, not this route's own scope to invent
unprompted.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from ports.compute import ComputePort
from ports.graph import GraphPort
from schemas.compute import (
    CentralityMetric,
    CentralityRequest,
    CliqueMetricRequest,
    CommunityRequest,
)
from schemas.domain import CommunityId, NodeId, Principal, Subgraph, TxId

from .access import narrow_to_visible
from .jobs import JobQueue
from .working_set.service import WorkingSetService

JOB_TYPE_COMPUTE_METRIC = "compute_metric"

#: `02_GLASS_FRONTEND.md` §5's own performance budget — see this module's own docstring.
SYNC_NODE_LIMIT = 20_000

ComputeMetricName = CentralityMetric | Literal["communities", "clique_metric"]

_CENTRALITY_METRICS: frozenset[str] = frozenset(
    {
        "degree",
        "weighted_degree",
        "betweenness",
        "eigenvector",
        "pagerank",
        "clustering_coefficient",
    }
)

_MetricResult = dict[NodeId, float] | dict[NodeId, CommunityId]


class ComputeMetricRequest(BaseModel):
    """Only `clique_metric` reads `k_min`/`k_max` — every other metric ignores both, the same
    "harmless unused field" shape `CliqueMetricRequest` itself already has."""

    k_min: int = 4
    k_max: int = 30


class ComputeMetricAccepted(BaseModel):
    """`values`/`communities` are mutually exclusive, never both set. Kept as two concretely-typed
    fields rather than one `dict[NodeId, float] | dict[NodeId, CommunityId]` union: Pydantic's
    smart-union validation coerces a numeric-looking community label ("0", "1"...) into a `float`
    on a plain string-vs-float ambiguity, which would misreport a categorical id as a score — a
    real ambiguity checked and avoided, not a hypothetical one guarded against on principle
    alone."""

    mode: Literal["sync", "job"]
    values: dict[NodeId, float] | None = None
    communities: dict[NodeId, CommunityId] | None = None
    job_id: str | None = None


async def _run_metric(
    metric: str, subgraph: Subgraph, compute: ComputePort, *, k_min: int, k_max: int
) -> _MetricResult:
    if metric in _CENTRALITY_METRICS:
        centrality_metric: CentralityMetric = metric  # type: ignore[assignment]
        return await compute.centrality(
            CentralityRequest(subgraph=subgraph, metric=centrality_metric)
        )
    if metric == "communities":
        return await compute.communities(CommunityRequest(subgraph=subgraph))
    if metric == "clique_metric":
        return await compute.clique_metric(
            CliqueMetricRequest(subgraph=subgraph, k_min=k_min, k_max=k_max)
        )
    raise ValueError(f"unsupported compute metric: {metric!r}")


def _result_to_response(
    metric: str, result: _MetricResult, *, mode: Literal["sync", "job"]
) -> ComputeMetricAccepted:
    if metric == "communities":
        return ComputeMetricAccepted(mode=mode, communities=result)  # type: ignore[arg-type]
    return ComputeMetricAccepted(mode=mode, values=result)  # type: ignore[arg-type]


async def _build_visible_subgraph(
    working_set: WorkingSetService, investigation_id: str, graph: GraphPort, principal: Principal
) -> Subgraph:
    nodes, _edges = await working_set.current_membership(investigation_id)
    node_ids = [n.id for n in nodes]
    result = await narrow_to_visible(graph, node_ids, principal)
    return Subgraph(nodes=list(result.nodes.values()), edges=result.edges)


async def submit_compute_metric(
    metric: ComputeMetricName,
    investigation_id: str,
    body: ComputeMetricRequest,
    *,
    working_set: WorkingSetService,
    graph: GraphPort,
    principal: Principal,
    compute: ComputePort,
    jobs: JobQueue,
) -> ComputeMetricAccepted:
    subgraph = await _build_visible_subgraph(working_set, investigation_id, graph, principal)

    if len(subgraph.nodes) < SYNC_NODE_LIMIT:
        result = await _run_metric(metric, subgraph, compute, k_min=body.k_min, k_max=body.k_max)
        return _result_to_response(metric, result, mode="sync")

    job_id = await jobs.submit(
        JOB_TYPE_COMPUTE_METRIC,
        {
            "metric": metric,
            "subgraph": subgraph.model_dump(mode="json"),
            "k_min": body.k_min,
            "k_max": body.k_max,
        },
    )
    return ComputeMetricAccepted(mode="job", job_id=job_id)


async def run_compute_metric_job(
    payload: dict[str, Any], *, graph: GraphPort, tx: TxId, compute: ComputePort
) -> dict[str, Any]:
    """`graph`/`tx` are unused, present only to satisfy `JobWorker`'s one fixed dispatch shape
    (`(payload, *, graph, tx)`, `services/api/worker.py`) — the `Subgraph` in `payload` was already
    access-filtered by `submit_compute_metric` before this job was ever queued, so nothing here
    re-touches the store. `compute` is bound at registration time (`functools.partial`), the same
    process-wide-configuration shape `run_resolve_entity_type_job` already established for
    `ontology`/`scheme`/`valkey`."""
    metric = str(payload["metric"])
    subgraph = Subgraph.model_validate(payload["subgraph"])
    result = await _run_metric(
        metric,
        subgraph,
        compute,
        k_min=int(payload.get("k_min", 4)),
        k_max=int(payload.get("k_max", 30)),
    )
    if metric == "communities":
        return {"communities": result}
    return {"values": result}


__all__ = [
    "JOB_TYPE_COMPUTE_METRIC",
    "SYNC_NODE_LIMIT",
    "ComputeMetricAccepted",
    "ComputeMetricName",
    "ComputeMetricRequest",
    "run_compute_metric_job",
    "submit_compute_metric",
]
