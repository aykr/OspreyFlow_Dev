"""The standing rule that access control lives in the adapter, applied to
`explain_cluster` (`GET .../resolution/explain/{cluster_id}`) —
found alongside the same `set_resolution_threshold` gap, the fourth instance
of one repeated pattern, and worse in kind: this route
resolves a caller-named `cluster_id` to its member node ids from `source_fidelity_nodes` — the
investigation-*shared*, unfiltered node set — with nothing that previously checked every member
was visible to the calling principal before returning `member_node_ids` directly. A lower-
clearance principal naming a cluster containing a hidden node got that node's own id back
verbatim, not merely an aggregate count.

Uses the **real** `graph_arcadedb` adapter, not `FakeGraphPort`, for the same reason every other
access-control test in this package does: a fake's own simulated filtering could drift from the
real adapter's.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from conduit_common.identity import new_node_id, now_utc
from services.api.working_set.models import ClusterNotFoundError
from services.api.working_set.service import WorkingSetService

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
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


def _stub_node(node_id: str, classification: str, cluster_id: str) -> Node:
    return Node(
        id=node_id,
        type="Endpoint",
        properties={},
        provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        audit=AuditStub(created_at=now_utc(), created_by="loader-1"),
        resolution=ResolutionState(cluster_id=cluster_id),
    )


async def test_explain_cluster_omits_a_hidden_member_rather_than_naming_its_id(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        official_write = _node_write("OFFICIAL", "+441111111111")
        secret_write = _node_write("SECRET", "+442222222222")
        tx = await graph.begin_transaction()
        (official_id, secret_id) = await graph.upsert_nodes([official_write, secret_write], tx)
        await graph.commit_transaction(tx)

        cluster_id = official_id
        store = FakeWorkingSetStore()
        await store.add_nodes(
            INVESTIGATION,
            [
                _stub_node(official_id, "OFFICIAL", cluster_id=cluster_id),
                _stub_node(secret_id, "SECRET", cluster_id=cluster_id),
            ],
        )

        service = WorkingSetService(graph, store, load_uk_le_scheme())

        official_view = await service.explain_cluster(INVESTIGATION, cluster_id, OFFICIAL)
        assert official_view.member_node_ids == [official_id]
        assert secret_id not in official_view.member_node_ids

        secret_view = await service.explain_cluster(INVESTIGATION, cluster_id, SECRET)
        assert set(secret_view.member_node_ids) == {official_id, secret_id}


async def test_explain_cluster_of_only_hidden_members_is_indistinguishable_from_not_found(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        secret_write = _node_write("SECRET", "+443333333333")
        tx = await graph.begin_transaction()
        (secret_id,) = await graph.upsert_nodes([secret_write], tx)
        await graph.commit_transaction(tx)

        cluster_id = secret_id
        store = FakeWorkingSetStore()
        await store.add_nodes(
            INVESTIGATION, [_stub_node(secret_id, "SECRET", cluster_id=cluster_id)]
        )

        service = WorkingSetService(graph, store, load_uk_le_scheme())

        with pytest.raises(ClusterNotFoundError):
            await service.explain_cluster(INVESTIGATION, cluster_id, OFFICIAL)
