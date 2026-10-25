"""`WorkingSetService.visible_edge` — the one question link notes ask before they read or write
anything: is this link in this investigation's working set, and does this principal's own
handling clearance let them see it (and both of its ends)?

The rule is the same one `_project` applies to every other read — an edge is visible only if its
own handling clears *and* both endpoints are visible — so a link a principal cannot see answers
exactly as a link that does not exist (`None`), and neither can be told from the other."""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.working_set.service import WorkingSetService

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

from .fakes import FakeGraphPort, FakeWorkingSetStore

SCHEME = load_uk_le_scheme()
OFFICIAL_READER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
SECRET_READER = Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1")


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification,
        handling_code="P",
        originator="unit-1",
        owning_unit="unit-1",
    )


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _audit() -> AuditStub:
    return AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1")


def node(node_id: str, classification: str = "OFFICIAL") -> Node:
    return Node(
        id=node_id,
        type="Person",
        provenance=_provenance(),
        handling=_handling(classification),
        audit=_audit(),
    )


def edge(edge_id: str, source: str, target: str, classification: str = "OFFICIAL") -> Edge:
    return Edge(
        id=edge_id,
        type="ASSOCIATED_WITH",
        source=source,
        target=target,
        provenance=_provenance(),
        handling=_handling(classification),
        audit=_audit(),
    )


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]))
    return WorkingSetService(graph, store, SCHEME)


async def _store_with(
    nodes: list[Node], edges: list[Edge], investigation_id: str = "inv-1"
) -> FakeWorkingSetStore:
    store = FakeWorkingSetStore()
    await store.add_nodes(investigation_id, nodes)
    await store.add_edges(investigation_id, edges)
    return store


async def test_a_link_in_the_working_set_that_the_principal_may_see_is_returned() -> None:
    store = await _store_with([node("a"), node("b")], [edge("e1", "a", "b")])
    found = await _service(store).visible_edge("inv-1", "e1", OFFICIAL_READER)
    assert found is not None
    assert found.id == "e1"


async def test_a_link_that_is_not_in_the_working_set_is_none() -> None:
    store = await _store_with([node("a"), node("b")], [edge("e1", "a", "b")])
    assert await _service(store).visible_edge("inv-1", "no-such-link", OFFICIAL_READER) is None


async def test_a_link_in_another_investigations_working_set_is_none() -> None:
    store = await _store_with([node("a"), node("b")], [edge("e1", "a", "b")], "inv-other")
    assert await _service(store).visible_edge("inv-1", "e1", OFFICIAL_READER) is None


async def test_a_link_above_the_principals_clearance_is_none() -> None:
    store = await _store_with([node("a"), node("b")], [edge("e1", "a", "b", "SECRET")])
    service = _service(store)
    assert await service.visible_edge("inv-1", "e1", OFFICIAL_READER) is None
    assert await service.visible_edge("inv-1", "e1", SECRET_READER) is not None


async def test_a_link_with_an_end_the_principal_may_not_see_is_none() -> None:
    """An edge whose own marking would pass but which points at a hidden node would itself
    disclose that node's existence — the same reason `_project` excludes it."""
    store = await _store_with([node("a"), node("b", "SECRET")], [edge("e1", "a", "b")])
    service = _service(store)
    assert await service.visible_edge("inv-1", "e1", OFFICIAL_READER) is None
    assert await service.visible_edge("inv-1", "e1", SECRET_READER) is not None


async def test_a_link_whose_end_has_left_the_working_set_is_none() -> None:
    store = await _store_with([node("a")], [edge("e1", "a", "b")])
    assert await _service(store).visible_edge("inv-1", "e1", OFFICIAL_READER) is None
