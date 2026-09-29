"""`narrow_to_visible` (`services/api/access.py`) — the specific gap found and fixed while
building `ComputePort`'s first real caller (Phase 7 Stage 3), named directly rather than left
implicit: a test
proving the exact defect, not only the composed access-control property one hop up.

**The defect, precisely.** `GraphPort.expand(node_ids, depth=1)` traverses one hop past its own
`node_ids` — a real, *visible* neighbour outside that requested set can come back as one of
`subgraph.nodes` and, more importantly, its edge to a requested node comes back in
`subgraph.edges` regardless. `narrow_to_visible`'s own node filter (`n.id in requested`) correctly
drops that neighbour from `VisibilityResult.nodes` — but before this fix, `VisibilityResult.edges`
was `subgraph.edges` verbatim, so the edge naming that dropped neighbour survived anyway: a result
whose own `edges` can reference a node absent from its own `nodes`. **This is not the same
property `tests/services/api/working_set/test_compute_access_control.py` proves** — that test
exercises a *hidden-classification* neighbour, which `GraphPort.expand` itself already excludes
from both `nodes` and `edges` before `narrow_to_visible` ever runs; this test exercises a
*visible-but-out-of-scope* neighbour, which `expand` has no reason to exclude at all, since
nothing about it is a classification violation — only `narrow_to_visible`'s own node-set narrowing
makes it out-of-scope, and only this fix carries that narrowing through to `edges` too.

Uses the **real** `graph_arcadedb` adapter, the same reasoning as every other test in this family.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.access import narrow_to_visible

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from schemas.domain import EdgeWrite, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)

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


async def test_an_edge_to_a_visible_but_unrequested_neighbour_is_excluded(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        node_a = _node_write("OFFICIAL", "+441111111111")
        # `N` is fully visible to `OFFICIAL` (same classification) — the point of this test is
        # that it is excluded for being *out of the requested scope*, not for being hidden.
        node_n = _node_write("OFFICIAL", "+442222222222")
        tx = await graph.begin_transaction()
        (id_a, id_n) = await graph.upsert_nodes([node_a, node_n], tx)
        edge_an = EdgeWrite(
            id=new_edge_id(),
            type="SAME_AS",
            source=id_a,
            target=id_n,
            properties={"score": 1.0},
            provenance=_provenance(),
            handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
            created_by="loader-1",
            created_at=now_utc(),
        )
        await graph.upsert_edges([edge_an], tx)
        await graph.commit_transaction(tx)

        # Only `A` is requested — `N` is a real, visible, one-hop neighbour `expand`'s own
        # `depth=1` traversal will reach, but it was never asked for.
        result = await narrow_to_visible(graph, [id_a], OFFICIAL)

        assert set(result.nodes) == {id_a}
        # The assertion that fails without this fix: an edge naming `N`, a node absent from
        # `result.nodes`, must never appear in `result.edges` either.
        assert result.edges == []
