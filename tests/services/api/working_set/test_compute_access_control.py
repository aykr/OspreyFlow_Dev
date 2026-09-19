"""Standing rule 2, applied to `ComputePort`'s first real caller (`services/api/compute_routes.py`,
Phase 7 Stage 3) — the composed claim `packages/schemas/compute.py`'s own docstring disclosed as
owed: "that composed claim is owed by whichever stage builds `ComputePort`'s first real caller."

`WorkingSetService.current_membership` is **deliberately unfiltered** (its own docstring). Feeding
it straight into `ComputePort` would let a hidden node's own existence leak through a *visible*
node's own degree or centrality score — `CLAUDE.md` rule 3's concern named directly, and the same
shape of defect `test_resolution_threshold_access_control.py` and
`test_projection_access_control.py` already proved for resolution's own read/write paths. This
test proves the actual, composed
contract: seed a visible `A`, a visible `B` and a `SECRET` `H`, with edges `A–B` and `A–H`, and
assert `OFFICIAL`'s own computed degree for `A` is `1`, not `2` — the assertion that fails if a
future change ever feeds `current_membership`'s own unfiltered edges straight to `ComputePort`.

Uses the **real** `graph_arcadedb` adapter and the **real** `ComputeRustworkxAdapter` — the same
"no fake stands in for an access-control claim" discipline every other test in this family follows
(`07_BUILD_PLAN.md`'s own `FakeGraphPort` gaps entry). `FakeWorkingSetStore` and `_FakeJobQueue`
are still fakes here, deliberately: neither the working-set store's own storage logic nor the job
queue's own dispatch mechanics are what this test is about — only whether the population handed to
`ComputePort` was narrowed to what `OFFICIAL` can actually see.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.compute_routes import ComputeMetricRequest, submit_compute_metric
from services.api.working_set.service import WorkingSetService

from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

from .fakes import FakeWorkingSetStore

pytestmark = pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)

INVESTIGATION = "inv-1"
SHARED_UNIT = "unit-1"
OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit=SHARED_UNIT)


class _FakeJobQueue:
    """Never actually called here — three visible nodes never reach `SYNC_NODE_LIMIT`. Present
    only to satisfy `submit_compute_metric`'s own parameter, the same "fake the uninvolved
    dependency" shape `test_supersede.py`'s own `_FakeJobQueue` already establishes."""

    async def submit(self, job_type: str, payload: dict[str, object]) -> str:
        raise AssertionError("this test's population never reaches the job-mode threshold")


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=datetime.now(UTC),
    )


def _handling(classification: str) -> dict[str, str | None]:
    return {
        "classification": classification,
        "handling_code": "P",
        "originator": SHARED_UNIT,
        "owning_unit": SHARED_UNIT,
        "action_code": None,
        "sanitisation_code": None,
    }


def _node_write(classification: str, value_normalised: str) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type="Endpoint",
        properties={"value_normalised": value_normalised},
        provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        created_by="loader-1",
        created_at=now_utc(),
    )


def _stub_node(node_id: str, classification: str) -> Node:
    return Node(
        id=node_id,
        type="Endpoint",
        properties={},
        provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        audit=AuditStub(created_at=now_utc(), created_by="loader-1"),
    )


def _stub_edge(edge_id: str, source: str, target: str) -> Edge:
    return Edge(
        id=edge_id,
        type="SAME_AS",
        source=source,
        target=target,
        properties={"score": 1.0},
        provenance=_provenance(),
        handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
        audit=AuditStub(created_at=now_utc(), created_by="loader-1"),
    )


async def test_a_hidden_neighbour_never_inflates_a_visible_nodes_computed_degree(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        node_a = _node_write("OFFICIAL", "+441111111111")
        node_b = _node_write("OFFICIAL", "+442222222222")
        node_h = _node_write("SECRET", "+443333333333")
        tx = await graph.begin_transaction()
        (id_a, id_b, id_h) = await graph.upsert_nodes([node_a, node_b, node_h], tx)
        edge_ab = EdgeWrite(
            id=new_edge_id(),
            type="SAME_AS",
            source=id_a,
            target=id_b,
            properties={"score": 1.0},
            provenance=_provenance(),
            handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
            created_by="loader-1",
            created_at=now_utc(),
        )
        edge_ah = EdgeWrite(
            id=new_edge_id(),
            type="SAME_AS",
            source=id_a,
            target=id_h,
            properties={"score": 1.0},
            provenance=_provenance(),
            handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
            created_by="loader-1",
            created_at=now_utc(),
        )
        await graph.upsert_edges([edge_ab, edge_ah], tx)
        await graph.commit_transaction(tx)

        # The working set's own membership carries the full, unfiltered population — exactly
        # `current_membership`'s own "deliberately unfiltered" contract — including `H` and both
        # edges, regardless of who will eventually call the compute route.
        store = FakeWorkingSetStore()
        await store.add_nodes(
            INVESTIGATION,
            [
                _stub_node(id_a, "OFFICIAL"),
                _stub_node(id_b, "OFFICIAL"),
                _stub_node(id_h, "SECRET"),
            ],
        )
        await store.add_edges(
            INVESTIGATION,
            [
                _stub_edge(edge_ab.id, id_a, id_b),
                _stub_edge(edge_ah.id, id_a, id_h),
            ],
        )

        working_set = WorkingSetService(graph, store, load_uk_le_scheme())
        compute = ComputeRustworkxAdapter()

        accepted = await submit_compute_metric(
            "degree",
            INVESTIGATION,
            ComputeMetricRequest(),
            working_set=working_set,
            graph=graph,
            principal=OFFICIAL,
            compute=compute,
            jobs=_FakeJobQueue(),  # type: ignore[arg-type]
        )

        assert accepted.mode == "sync"
        assert accepted.values is not None
        # `H` itself must never appear at all — the same existence-leak discipline standing rule 3
        # names for any filtered node, not merely a degree miscount for `A`.
        assert id_h not in accepted.values
        # The real check: `A`'s own computed degree counts only the `A–B` edge `OFFICIAL` can see.
        # If a future change ever feeds `current_membership`'s unfiltered edges straight into
        # `ComputePort`, this becomes `2.0` instead.
        assert accepted.values[id_a] == 1.0
