"""The standing rule that access control lives in the adapter, applied to
`_manual_assertion`'s own write path — this phase's own third question.
`source_fidelity_nodes` (`FakeWorkingSetStore` here, `ValkeyWorkingSetStore`
for real) is the *investigation-shared* node set, not a projection scoped to the calling
principal's own clearance — two principals can share one investigation at different clearances,
both authorized via the same `org_unit`. `_manual_assertion` (`services/api/working_set/
service.py`) re-verifies both nodes through `GraphPort.get_node(node_id, principal)` before
writing, the same principal-scoped check `expand` already uses two lines later in the same method.

Uses the **real** `graph_arcadedb` adapter, not `FakeGraphPort` — the same reasoning
`tests/resolve/test_projection_access_control.py` already established: a fake's own simulated
access control could drift from the real adapter's, proving nothing about the actual boundary.
`FakeWorkingSetStore` is still a fake here, deliberately — the working-set store's own logic is
not what this test is about.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.working_set.models import NodeNotInWorkingSetError
from services.api.working_set.service import WorkingSetService

from conduit_common.identity import new_node_id, now_utc
from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    ExpandRequest,
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

SCHEME = load_uk_le_scheme()
INVESTIGATION = "inv-1"
SHARED_UNIT = "unit-1"
OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit=SHARED_UNIT)
SECRET = Principal(id="analyst-secret", clearance="SECRET", org_unit=SHARED_UNIT)


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


def _node_write(classification: str) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type="Endpoint",
        properties={"value_normalised": f"+44{classification}"},
        provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        created_by="loader-1",
        created_at=now_utc(),
    )


async def test_manual_link_denies_a_lower_clearance_principal_naming_a_hidden_node(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        official_write = _node_write("OFFICIAL")
        secret_write = _node_write("SECRET")
        tx = await graph.begin_transaction()
        (official_id, secret_id) = await graph.upsert_nodes([official_write, secret_write], tx)
        await graph.commit_transaction(tx)

        # Both nodes are in the *shared* working set — as if the SECRET-cleared colleague's own
        # earlier `expand` had already pulled the SECRET node in for both principals to nominally
        # share, the real, permitted shape this test exists to check.
        store = FakeWorkingSetStore()
        await store.add_nodes(
            INVESTIGATION,
            [
                Node(
                    id=official_id,
                    type="Endpoint",
                    properties={},
                    provenance=_provenance(),
                    handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
                    audit=AuditStub(created_at=now_utc(), created_by="loader-1"),
                ),
                Node(
                    id=secret_id,
                    type="Endpoint",
                    properties={},
                    provenance=_provenance(),
                    handling=_handling("SECRET"),  # type: ignore[arg-type]
                    audit=AuditStub(created_at=now_utc(), created_by="loader-1"),
                ),
            ],
        )

        service = WorkingSetService(graph, store, SCHEME)

        with pytest.raises(NodeNotInWorkingSetError):
            await service.manual_link(INVESTIGATION, official_id, secret_id, OFFICIAL)

        # Never written — the existence-leak discipline means denial happens before any edge does.
        subgraph = await graph.expand(
            ExpandRequest(node_ids=[official_id], depth=1, edge_types=["SAME_AS"]), SECRET
        )
        assert subgraph.edges == []

        # The same call succeeds for the principal who can actually see both nodes.
        delta, _entry = await service.manual_link(INVESTIGATION, official_id, secret_id, SECRET)
        assert delta.merged == 1
