"""Ownership traced for the reader (`spec/06_DECISIONS.md` ADR-109 phase C), against a live
ArcadeDB — the access step is the adapter's, and only the real one can show it.

What a mistake would do, and the case that catches it:

- a SECRET owner (or a SECRET link) counted for an OFFICIAL reader would tell them it exists through
  a share they cannot account for (rule 3) — the reader's trace must equal the trace of the
  structure without it (`test_a_hidden_owner_leaves_the_trace_as_if_it_were_absent`);
- a structure deeper than the limit traced to the limit and reported as whole would understate
  every share beyond it (rule 2) (`test_a_structure_deeper_than_the_limit_is_refused`);
- an entity the reader cannot see answered with an empty trace rather than not found would confirm
  it exists (`test_an_entity_the_reader_cannot_see_is_not_found`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.ownership import trace_for
from services.api.suppression import NodeNotVisibleError

from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.compute import OwnershipTooComplex
from schemas.domain import EdgeWrite, Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef

ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
OFFICIAL = Principal(id="reader", clearance="OFFICIAL", org_unit="u")
SECRET = Principal(id="cleared", clearance="SECRET", org_unit="u")
NOW = datetime.now(UTC)
PROVENANCE = Provenance(
    state=ProvenanceState.ASSERTED,
    sources=[SourceRef(document_id="t", locator="r", excerpt_hash="")],
    first_seen=NOW,
)


def _handling(classification: str) -> Handling:
    return Handling(classification=classification, handling_code="P", originator="u", owning_unit="u")


def _node(node_type: str, name: str, classification: str = "OFFICIAL") -> NodeWrite:
    props = {"family_name": name} if node_type == "Person" else {"name": name}
    return NodeWrite(id=new_node_id(), type=node_type, properties=props, provenance=PROVENANCE,
                     handling=_handling(classification), created_by="t", created_at=NOW)  # fmt: skip


def _owns(source: str, target: str, percent: float, classification: str = "OFFICIAL") -> EdgeWrite:
    return EdgeWrite(id=new_edge_id(), type="BENEFICIAL_OWNER_OF", source=source, target=target,
                     properties={"percent": percent}, provenance=PROVENANCE,
                     handling=_handling(classification), created_by="t", created_at=NOW)  # fmt: skip


async def _write(graph, nodes: list[NodeWrite], edges: list[EdgeWrite]) -> list[str]:  # type: ignore[no-untyped-def]
    tx = await graph.begin_transaction()
    ids = await graph.upsert_nodes(nodes, tx)
    await graph.upsert_edges(edges, tx)
    await graph.commit_transaction(tx)
    return ids


async def test_a_hidden_owner_leaves_the_trace_as_if_it_were_absent() -> None:
    target, visible = _node("Organisation", "Target Ltd"), _node("Person", "Visible")
    hidden_person = _node("Person", "Hidden", "SECRET")
    hidden_company = _node("Organisation", "Hidden Holdings Ltd")
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _write(
            graph,
            [target, visible, hidden_person, hidden_company],
            [
                _owns(visible.id, target.id, 30),
                _owns(hidden_person.id, target.id, 50),  # a SECRET owner
                _owns(hidden_company.id, target.id, 20, "SECRET"),  # an OFFICIAL owner, SECRET link
                _owns(visible.id, hidden_company.id, 100),
            ],
        )
        seen = await trace_for(graph, ComputeRustworkxAdapter(), target.id, OFFICIAL)
        assert [(o.node_id, o.cumulative_percent) for o in seen.trace.owners] == [(visible.id, 30.0)]
        assert {n.id for n in seen.nodes} == {target.id, visible.id}

        cleared = await trace_for(graph, ComputeRustworkxAdapter(), target.id, SECRET)
        shares = {o.node_id: o.cumulative_percent for o in cleared.trace.owners}
        assert shares == {visible.id: 50.0, hidden_person.id: 50.0, hidden_company.id: 20.0}


async def test_a_structure_deeper_than_the_limit_is_refused() -> None:
    chain = [_node("Organisation", f"Layer {i} Ltd") for i in range(13)]
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _write(graph, chain, [_owns(a.id, b.id, 100) for a, b in zip(chain[1:], chain, strict=False)])
        with pytest.raises(OwnershipTooComplex):
            await trace_for(graph, ComputeRustworkxAdapter(), chain[0].id, OFFICIAL)
        # Within the limit, the same structure traces whole.
        whole = await trace_for(graph, ComputeRustworkxAdapter(), chain[3].id, OFFICIAL)
        assert len(whole.trace.owners) == 9


async def test_an_entity_the_reader_cannot_see_is_not_found() -> None:
    secret = _node("Organisation", "Secret Ltd", "SECRET")
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _write(graph, [secret], [])
        with pytest.raises(NodeNotVisibleError):
            await trace_for(graph, ComputeRustworkxAdapter(), secret.id, OFFICIAL)
