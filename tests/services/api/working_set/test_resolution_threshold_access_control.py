"""The standing rule that access control lives in the adapter, applied to
`set_resolution_threshold` itself — this phase's own fourth question.

`tests/resolve/test_projection_access_control.py` already proves `compute_clusters` is safe
*given already-filtered input*, and that `GraphPort.expand` filters out an edge if *either*
endpoint is hidden from the calling principal, regardless of the edge's own classification.
Checked against that: `set_resolution_threshold` feeding the *unfiltered* `source_fidelity_nodes`
population into `compute_clusters` (rather than the visible subset `expand` itself returned)
turns out **not** to leak through the `merged`/`split`/`affected` counts specifically — a node
with no visible edges is always an inert singleton in `compute_clusters`' union-find, at every τ,
so its mere presence in the unfiltered id list cannot change those three numbers. That rules out
the aggregate-count leak this test first went looking for.

**What the unfiltered population actually breaks: a write side effect, not a read leak.**
`compute_clusters` returns a full `NodeId -> ClusterId` mapping over whatever ids it is given, and
the unfiltered call therefore produced an entry for the hidden node too — its own singleton label,
independent of whatever a *different*, better-cleared principal's own earlier call had persisted
for it. `set_resolution_threshold` used to write that entry straight back into the shared store
for every node in `nodes_by_id`, meaning a principal who cannot see a node at all could silently
reset that node's own persisted `resolution.cluster_id` — collapsing state a higher-clearance
principal had legitimately established — purely by calling their own threshold endpoint. That is
an unauthorised mutation of state outside the caller's own view, not an information disclosure,
but it is the same boundary standing rule 3 draws for a write. The fix narrows both the
`compute_clusters` population *and* which nodes `updated_nodes` is allowed to touch to the
principal-visible subset `expand` returned, so a call that cannot see a node cannot move its
stored cluster state either.

Uses the **real** `graph_arcadedb` adapter, not `FakeGraphPort` — the same reasoning
`test_projection_access_control.py` and `test_manual_resolution_access_control.py` already
established: a fake's own simulated access control could drift from the real adapter's, proving
nothing about the actual boundary.
`FakeWorkingSetStore` is still a fake here, deliberately — the working-set store's own logic is
not what this test is about.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from services.api.working_set.service import WorkingSetService
from services.resolve.projection import THRESHOLD_BALANCED, THRESHOLD_BROAD

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    EdgeWrite,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    ResolutionState,
    SourceRef,
)

from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory
from .fakes import FakeWorkingSetStore

pytestmark = pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)

INVESTIGATION = "inv-1"
SHARED_UNIT = "unit-1"
OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit=SHARED_UNIT)


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


def _stub_node(node_id: str, classification: str, cluster_id: str | None) -> Node:
    return Node(
        id=node_id,
        type="Endpoint",
        properties={},
        provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        audit=AuditStub(created_at=now_utc(), created_by="loader-1"),
        resolution=ResolutionState(cluster_id=cluster_id),
    )


async def test_a_principal_blind_to_a_node_cannot_reset_its_persisted_cluster_state(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        official_write = _node_write("OFFICIAL", "+441111111111")
        secret_write = _node_write("SECRET", "+442222222222")
        tx = await graph.begin_transaction()
        (official_id, secret_id) = await graph.upsert_nodes([official_write, secret_write], tx)
        # No `SAME_AS`/`NOT_SAME_AS` edge between them at all — `OFFICIAL` cannot merge or split
        # this pair through any legitimate clustering of their own; the only way `secret_id`'s own
        # stored cluster state could move under an `OFFICIAL` call is the write-path bug itself.
        await graph.commit_transaction(tx)

        # Seed the shared store as if a `SECRET`-cleared colleague's own earlier `manual_link`
        # had already merged the pair — both nodes carry the same persisted `cluster_id`, the
        # real shape this test exists to protect.
        store = FakeWorkingSetStore()
        await store.add_nodes(
            INVESTIGATION,
            [
                _stub_node(official_id, "OFFICIAL", cluster_id=official_id),
                _stub_node(secret_id, "SECRET", cluster_id=official_id),
            ],
        )
        await store.set_threshold(INVESTIGATION, THRESHOLD_BALANCED)

        service = WorkingSetService(graph, store, load_uk_le_scheme())

        # `OFFICIAL` never receives `secret_id` at all, so this call's own `affected`/`merged`
        # counts must be zero — there is nothing this principal's own clustering could have
        # changed with no visible resolution edges.
        delta = await service.set_resolution_threshold(INVESTIGATION, THRESHOLD_BROAD, OFFICIAL)
        assert delta.merged == 0
        assert delta.affected == 0
        assert delta.affected_cluster_ids == {}

        # The real check: `secret_id`'s own persisted cluster state, established by a principal
        # `OFFICIAL` cannot see, must survive a call `OFFICIAL` was never entitled to make on its
        # behalf.
        nodes_by_id = await store.source_fidelity_nodes(INVESTIGATION)
        assert nodes_by_id[secret_id].resolution.cluster_id == official_id
