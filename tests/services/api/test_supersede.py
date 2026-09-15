"""The `supersede_node` sync/job routing decision —
`docs/07_BUILD_PLAN.md` Phase 3's job-based-path bullet,
`01_DOMAIN_MODEL.md` §8.2's measured ~41s/5,000-degree figure. Exercised
against minimal fakes, not a live ArcadeDB or Valkey: the thing under
test is the *decision*, not `GraphPort.supersede_node` or `JobQueue`
itself.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.supersede import (
    JOB_TYPE_SUPERSEDE_NODE,
    submit_supersede_node,
)

from schemas.domain import (
    Handling,
    NeighbourhoodStats,
    NodeId,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    TxId,
)

PRINCIPAL = Principal(id="reviewer-1", clearance="OFFICIAL", org_unit="unit-1")


def _replacement() -> NodeWrite:
    return NodeWrite(
        id="new-node-id",
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        created_by="reviewer-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class _FakeGraph:
    def __init__(self, degree: int) -> None:
        self.degree = degree
        self.supersede_calls: list[NodeId] = []

    async def neighbourhood_stats(
        self, node_id: NodeId, principal: Principal
    ) -> NeighbourhoodStats:
        return NeighbourhoodStats(node_id=node_id, degree=self.degree)

    async def supersede_node(self, node_id: NodeId, replacement: NodeWrite, tx: TxId) -> NodeId:
        self.supersede_calls.append(node_id)
        return "new-node-id"


class _FakeJobQueue:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, dict[str, object]]] = []

    async def submit(self, job_type: str, payload: dict[str, object]) -> str:
        self.submitted.append((job_type, payload))
        return "job-1"


async def test_below_threshold_runs_synchronously() -> None:
    graph = _FakeGraph(degree=10)
    jobs = _FakeJobQueue()

    outcome = await submit_supersede_node(
        "node-1",
        _replacement(),
        "tx-1",
        graph=graph,  # type: ignore[arg-type]
        principal=PRINCIPAL,
        jobs=jobs,  # type: ignore[arg-type]
        degree_threshold=500,
    )

    assert outcome.mode == "sync"
    assert outcome.result_node_id == "new-node-id"
    assert outcome.job_id is None
    assert graph.supersede_calls == ["node-1"]
    assert jobs.submitted == []


async def test_at_or_above_threshold_enqueues_a_job_instead_of_blocking() -> None:
    graph = _FakeGraph(degree=500)
    jobs = _FakeJobQueue()

    outcome = await submit_supersede_node(
        "node-1",
        _replacement(),
        "tx-1",
        graph=graph,  # type: ignore[arg-type]
        principal=PRINCIPAL,
        jobs=jobs,  # type: ignore[arg-type]
        degree_threshold=500,
    )

    assert outcome.mode == "job"
    assert outcome.job_id == "job-1"
    assert outcome.result_node_id is None
    assert graph.supersede_calls == []  # never called synchronously
    (job_type, payload) = jobs.submitted[0]
    assert job_type == JOB_TYPE_SUPERSEDE_NODE
    assert payload["node_id"] == "node-1"
    assert payload["degree_at_submission"] == 500
