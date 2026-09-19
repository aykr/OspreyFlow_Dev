"""Standing rule 2: every read path gets its own access-control test, no exceptions for internal
ones. `services/resolve/projection.py`'s `compute_clusters` is a pure union-find over whatever
edges it is handed — the right design, since it inherits the principal filter its caller already
applied at fetch (`WorkingSetService.set_resolution_threshold`'s own docstring: "the same access
filter every other read already goes through... `GraphPort.expand(..., principal)`"). But nothing
enforces that a caller actually filtered first. `compute_clusters` itself takes no `principal` at
all, so a future caller that fetched unfiltered would silently produce a clustering that merges
nodes a principal cannot see, and no existing test would fail — `tests/services/api/working_set/
test_resolution_threshold.py`'s own `FakeGraphPort` (`fakes.py`) ignores `principal` entirely and
always returns the same fixed `Subgraph`, so it cannot catch this: it isn't testing access control
at all, only `compute_clusters`' own logic given already-filtered input.

This test proves the actual, composed contract using the real adapter, not a fake: seed a `SAME_AS`
edge between an `OFFICIAL` `Endpoint` and a `SECRET` one, fetch through `GraphPort.expand` — the
same call the real caller makes — as two different principals, and feed each principal's own
result into `compute_clusters` directly. The `OFFICIAL` principal must never see the two nodes
merge, because it never received the `SECRET` node or its edge in the first place.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ports.graph import GraphPort
from schemas.domain import EdgeWrite, ExpandRequest, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef

from services.resolve.projection import THRESHOLD_BALANCED, compute_clusters

from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)

OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit="unit-1")
SECRET = Principal(id="analyst-secret", clearance="SECRET", org_unit="unit-1")


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
        "originator": "unit-1",
        "owning_unit": "unit-1",
        "action_code": None,
        "sanitisation_code": None,
    }


def _endpoint(classification: str, value_normalised: str) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type="Endpoint",
        properties={"value_normalised": value_normalised},
        provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        created_by="loader-1",
        created_at=now_utc(),
    )


async def test_a_hidden_endpoint_never_joins_its_same_as_cluster_for_an_unauthorised_principal(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        visible = _endpoint("OFFICIAL", "+441111111111")
        hidden = _endpoint("SECRET", "+442222222222")
        tx = await adapter.begin_transaction()
        (visible_id, hidden_id) = await adapter.upsert_nodes([visible, hidden], tx)
        same_as = EdgeWrite(
            id=new_edge_id(),
            type="SAME_AS",
            source=visible_id,
            target=hidden_id,
            properties={"score": 1.0},
            provenance=_provenance(),
            handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
            created_by="loader-1",
            created_at=now_utc(),
        )
        await adapter.upsert_edges([same_as], tx)
        await adapter.commit_transaction(tx)

        request = ExpandRequest(
            node_ids=[visible_id], depth=1, edge_types=["SAME_AS", "NOT_SAME_AS"]
        )

        official_subgraph = await adapter.expand(request, OFFICIAL)
        secret_subgraph = await adapter.expand(request, SECRET)

        official_same_as = [e for e in official_subgraph.edges if e.type == "SAME_AS"]
        secret_same_as = [e for e in secret_subgraph.edges if e.type == "SAME_AS"]

        official_clusters = compute_clusters(
            [visible_id, hidden_id], official_same_as, [], THRESHOLD_BALANCED
        )
        secret_clusters = compute_clusters(
            [visible_id, hidden_id], secret_same_as, [], THRESHOLD_BALANCED
        )

        # The `SECRET` principal sees the real edge and the two nodes cluster together.
        assert secret_clusters[visible_id] == secret_clusters[hidden_id]

        # The `OFFICIAL` principal never received the hidden node's own edge, so
        # `compute_clusters`' own "every input id gets a cluster, including a singleton" rule
        # (`projection.py`'s own docstring) gives each node its own — the two must differ, which
        # is only true because the fetch above filtered first. This is the assertion that fails
        # if a future caller ever fetches unfiltered.
        assert official_clusters[visible_id] != official_clusters[hidden_id]
