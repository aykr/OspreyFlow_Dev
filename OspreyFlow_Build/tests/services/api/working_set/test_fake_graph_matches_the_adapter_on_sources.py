"""Rule 15: the working-set fakes refuse and withhold what the adapter does (ADR-130 Amendment 2),
so a read that forgot `sources_in_full()` shows red here and not only against ArcadeDB. The
adapter's own behaviour is `tests/adapters/graph_arcadedb/test_sources_withheld_live.py`."""

from __future__ import annotations

import pytest

from ontology.handling import sources_in_full
from schemas.domain import EdgeWrite, Principal, Provenance, ProvenanceState, Subgraph

from ..test_link_changes import SupersedingGraph
from .fakes import FakeGraphPort
from .test_visible_link import edge, node

TWO = ["Z1001ZZ", "Z1002ZZ"]
SCOPED = Principal(id="a-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[TWO[0]])


def _graph() -> FakeGraphPort:
    a = node("a").model_copy(update={"datasets": list(TWO)})
    b = node("b").model_copy(update={"datasets": list(TWO)})
    link = edge("ab", "a", "b").model_copy(update={"datasets": list(TWO)})
    return FakeGraphPort(Subgraph(nodes=[a, b], edges=[link]), graph_nodes=[a, b])


def _withheld_write() -> EdgeWrite:
    base = edge("ab", "a", "b")
    return EdgeWrite(
        id="new",
        type=base.type,
        source="a",
        target="b",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[],
            sources_withheld=True,
            first_seen=base.provenance.first_seen,
        ),
        handling=base.handling,
        created_by="x",
        created_at=base.audit.created_at,
    )


async def test_get_node_withholds_for_a_scoped_reader_and_not_in_full() -> None:
    graph = _graph()
    (await graph.get_nodes(["a"], SCOPED))[0]
    got = await graph.get_node("a", SCOPED)
    assert got is not None and got.provenance.sources_withheld
    with sources_in_full():
        full = await graph.get_node("a", SCOPED)
    assert full is not None and not full.provenance.sources_withheld


async def test_edges_among_withholds_for_a_scoped_reader() -> None:
    graph = _graph()
    (link,) = await graph.edges_among(["a", "b"], SCOPED)
    assert link.provenance.sources_withheld and link.provenance.sources == []
    with sources_in_full():
        (full,) = await graph.edges_among(["a", "b"], SCOPED)
    assert not full.provenance.sources_withheld


async def test_upsert_edges_refuses_withheld_provenance_as_the_adapter_does() -> None:
    graph = _graph()
    tx = await graph.begin_transaction()
    with pytest.raises(ValueError, match="withheld"):
        await graph.upsert_edges([_withheld_write()], tx)


async def test_the_superseding_graph_refuses_withheld_provenance() -> None:
    graph = SupersedingGraph({"ab"})
    tx = await graph.begin_transaction()
    with pytest.raises(ValueError, match="withheld"):
        await graph.supersede_edge("ab", _withheld_write(), tx)
