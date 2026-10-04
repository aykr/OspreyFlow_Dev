"""Branching a chosen set of nodes into a new case (ADR-084).

The owner, 4 October 2026: select some nodes, send them to a new tab. The tab is a new case the
analyst owns, holding the selected nodes and the links between them, and the original is left as it
was. The service already forked a whole working set (`branch`); this file pins what is new:

- only the chosen nodes arrive, and only the links whose two ends are both chosen;
- access is applied exactly as for any read, so a node the principal may not see is not copied, and
  asking for it reads the same as asking for an id that does not exist (rules 3 and 4);
- a request that leaves nothing to copy is refused before a case is created, so no empty case is
  left behind;
- the whole-case branch is unchanged.

Written before `branch_contents` and `NothingToBranchError` existed, so the first run of each case
was red.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.working_set.models import NothingToBranchError
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
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), candidate_count=0)
    return WorkingSetService(graph, store, SCHEME)


async def _chain() -> FakeWorkingSetStore:
    """a - b - c - d, one link between each neighbouring pair."""
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [node("a"), node("b"), node("c"), node("d")])
    await store.add_edges(
        "inv-1", [edge("ab", "a", "b"), edge("bc", "b", "c"), edge("cd", "c", "d")]
    )
    return store


async def test_only_the_chosen_nodes_and_the_links_between_them_arrive() -> None:
    store = await _chain()
    nodes, edges, _ = await _service(store).branch_contents(
        "inv-1", OFFICIAL_READER, node_ids=["a", "b", "d"]
    )
    assert sorted(n.id for n in nodes) == ["a", "b", "d"]
    # bc and cd each have one end outside the choice; only ab has both.
    assert [e.id for e in edges] == ["ab"]


async def test_a_branch_of_a_choice_goes_to_the_new_case_and_leaves_the_source_alone() -> None:
    store = await _chain()
    outcome = await _service(store).branch("inv-1", "inv-2", OFFICIAL_READER, node_ids=["b", "c"])
    assert sorted(n.id for n in outcome.delta.nodes) == ["b", "c"]
    assert [e.id for e in outcome.delta.edges] == ["bc"]
    assert await store.node_ids("inv-2") == {"b", "c"}
    assert await store.edge_ids("inv-2") == {"bc"}
    assert await store.node_ids("inv-1") == {"a", "b", "c", "d"}
    assert await store.edge_ids("inv-1") == {"ab", "bc", "cd"}


async def test_without_a_choice_the_whole_working_set_is_branched_as_before() -> None:
    store = await _chain()
    nodes, edges, _ = await _service(store).branch_contents("inv-1", OFFICIAL_READER)
    assert sorted(n.id for n in nodes) == ["a", "b", "c", "d"]
    assert sorted(e.id for e in edges) == ["ab", "bc", "cd"]


async def test_a_node_the_principal_may_not_see_is_not_copied() -> None:
    """Rule 3: the branch is filtered the way every read is. Catches a subset path that copies
    straight from the source-fidelity set without projecting it for the branching principal."""
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [node("a"), node("b", "SECRET")])
    await store.add_edges("inv-1", [edge("ab", "a", "b")])
    nodes, edges, _ = await _service(store).branch_contents(
        "inv-1", OFFICIAL_READER, node_ids=["a", "b"]
    )
    assert [n.id for n in nodes] == ["a"]
    assert edges == []
    # A reader who is cleared for it does get it.
    nodes, edges, _ = await _service(store).branch_contents(
        "inv-1", SECRET_READER, node_ids=["a", "b"]
    )
    assert sorted(n.id for n in nodes) == ["a", "b"]
    assert [e.id for e in edges] == ["ab"]


async def test_asking_for_a_hidden_node_and_for_one_that_does_not_exist_read_the_same() -> None:
    """Rule 4, existence: the answer for a hidden id must equal the answer for a made-up one, in
    what comes back and in the count, so the request cannot be used to probe for hidden nodes."""
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [node("a"), node("hidden", "SECRET")])
    service = _service(store)
    hidden = await service.branch_contents("inv-1", OFFICIAL_READER, node_ids=["a", "hidden"])
    ghost = await service.branch_contents("inv-1", OFFICIAL_READER, node_ids=["a", "ghost"])
    assert [n.id for n in hidden[0]] == [n.id for n in ghost[0]] == ["a"]
    assert hidden[1] == ghost[1] == []
    assert hidden[2] == ghost[2] == 0


async def test_a_choice_with_nothing_visible_is_refused_the_same_way_whatever_the_reason() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [node("hidden", "SECRET")])
    service = _service(store)
    with pytest.raises(NothingToBranchError):
        await service.branch_contents("inv-1", OFFICIAL_READER, node_ids=["hidden"])
    with pytest.raises(NothingToBranchError):
        await service.branch_contents("inv-1", OFFICIAL_READER, node_ids=["ghost"])
    with pytest.raises(NothingToBranchError):
        await service.branch_contents("inv-1", OFFICIAL_READER, node_ids=[])


async def test_a_refused_choice_writes_nothing_to_the_new_case() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [node("a")])
    with pytest.raises(NothingToBranchError):
        await _service(store).branch("inv-1", "inv-2", OFFICIAL_READER, node_ids=["ghost"])
    assert await store.node_ids("inv-2") == set()


async def test_a_choice_that_repeats_an_id_copies_the_node_once() -> None:
    store = await _chain()
    nodes, _, _ = await _service(store).branch_contents(
        "inv-1", OFFICIAL_READER, node_ids=["a", "a", "b"]
    )
    assert sorted(n.id for n in nodes) == ["a", "b"]
