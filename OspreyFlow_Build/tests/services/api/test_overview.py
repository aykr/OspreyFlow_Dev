"""The overview service — `spec/06_DECISIONS.md` ADR-057 (the Glass starts on an overview of the
graph). What is proven here is the Conduit's own part, against a fake store: the ranking, the
reconciliation of shown and not-shown figures, the access class in the cache key, and the typed cap
breach. `GraphPort.vault_subgraph`'s own access filtering and cap behaviour is the conformance
suite's (written before the ArcadeDB adapter implements it, `CLAUDE.md` rule 1); the fake graph
below filters by principal only so the service's half of that contract can be tested, which is
exactly the shape `test_projection_access_control.py` uses for the resolution projection.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from services.api.cache import principal_class
from services.api.overview import build_overview
from services.api.working_set.models import LimitExceededError

from ports.graph import SubgraphTooLarge
from schemas.compute import CommunityRequest
from schemas.domain import (
    AuditStub,
    Edge,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

FULL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
RESTRICTED = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2")


def _node(node_id: str, node_type: str = "Endpoint") -> Node:
    return Node(
        id=node_id,
        type=node_type,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling={  # type: ignore[arg-type]
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1"),
    )


def _edge(edge_id: str, source: str, target: str) -> Edge:
    return Edge(
        id=edge_id,
        type="TRANSACTED",
        source=source,
        target=target,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling={  # type: ignore[arg-type]
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1"),
    )


#: Twelve nodes in four communities: a (5, a chain), b (3), c (3), d (1); one edge crosses a to b.
_LABELS = {
    **{f"a{i}": "comm-a" for i in range(1, 6)},
    **{f"b{i}": "comm-z" for i in range(1, 4)},
    **{f"c{i}": "comm-c" for i in range(1, 4)},
    "d1": "comm-d",
}
_NODE_TYPES = {"a1": "Person"}
_EDGES = [
    ("a1", "a2"),
    ("a2", "a3"),
    ("a3", "a4"),
    ("a4", "a5"),
    ("b1", "b2"),
    ("b2", "b3"),
    ("c1", "c2"),
    ("c2", "c3"),
    ("a5", "b1"),
]


class _FakeGraph:
    """Filters by principal the way the adapter must, and raises `SubgraphTooLarge` with the counts
    of what the principal can *see* — never what exists."""

    def __init__(
        self, *, hidden_from: dict[str, set[str]] | None = None, without: set[str] | None = None
    ) -> None:
        self.hidden_from = hidden_from or {}
        self.without = without or set()
        self.calls: list[tuple[Principal, int, int]] = []

    async def vault_subgraph(
        self, principal: Principal, *, max_nodes: int, max_edges: int
    ) -> Subgraph:
        self.calls.append((principal, max_nodes, max_edges))
        hidden = self.hidden_from.get(principal.id, set()) | self.without
        node_ids = [n for n in _ALL_NODES if n not in hidden]
        edges = [(s, t) for s, t in _EDGES if s not in hidden and t not in hidden]
        if len(node_ids) > max_nodes:
            raise SubgraphTooLarge(nodes=len(node_ids), edges=None)
        if len(edges) > max_edges:
            raise SubgraphTooLarge(nodes=len(node_ids), edges=len(edges))
        return Subgraph(
            nodes=[_node(n, _NODE_TYPES.get(n, "Endpoint")) for n in node_ids],
            edges=[_edge(f"e-{s}-{t}", s, t) for s, t in edges],
            filtered_count=len(
                hidden
            ),  # what the adapter reports; the overview must not pass it on
        )


_ALL_NODES = [*_LABELS, "e1"]  # e1 is a node the algorithm does not label


class _FakeCompute:
    def __init__(self) -> None:
        self.calls = 0

    async def communities(self, req: CommunityRequest) -> dict[str, str]:
        self.calls += 1
        return {n.id: _LABELS[n.id] for n in req.subgraph.nodes if n.id in _LABELS}


class _FakeCache:
    """Keyed the way `CachedQuery` is: the query signature and the principal's access class."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], object] = {}
        self.puts = 0

    async def get(self, signature: str, principal: Principal) -> object | None:
        return self.store.get((signature, principal_class(principal)))

    async def put(self, signature: str, principal: Principal, result: object) -> None:
        self.puts += 1
        self.store[(signature, principal_class(principal))] = result


async def _overview(graph: _FakeGraph, principal: Principal = FULL, **kwargs: object):  # type: ignore[no-untyped-def]
    kwargs.setdefault("cache", _FakeCache())
    kwargs.setdefault("compute", _FakeCompute())
    return await build_overview(graph=graph, principal=principal, vault="paysim", **kwargs)  # type: ignore[arg-type]


async def test_the_largest_communities_come_first_and_ties_break_by_id() -> None:
    # comm-z's nodes come before comm-c's in the store, so only the id tie-break puts c first.
    overview = await _overview(_FakeGraph(), top=3)

    assert [c.id for c in overview.clusters] == ["comm-a", "comm-c", "comm-z"]
    assert [c.size for c in overview.clusters] == [5, 3, 3]


async def test_each_cluster_carries_its_type_counts_internal_edges_and_a_stable_sample() -> None:
    overview = await _overview(_FakeGraph(), top=3)

    a = overview.clusters[0]
    assert a.node_type_counts == {"Person": 1, "Endpoint": 4}
    assert a.dominant_type == "Endpoint"
    assert a.internal_edge_count == 4
    assert a.sample_node_ids == sorted(a.sample_node_ids)
    assert set(a.sample_node_ids) <= {f"a{i}" for i in range(1, 6)}


async def test_links_between_shown_communities_carry_their_edge_counts() -> None:
    overview = await _overview(_FakeGraph(), top=3)

    assert [
        (link.source_cluster, link.target_cluster, link.edge_count) for link in overview.links
    ] == [("comm-a", "comm-z", 1)]


async def test_what_is_not_shown_is_counted_exactly_and_everything_reconciles() -> None:
    """`CLAUDE.md` rule 2: never a silent slice. Every visible node is in a shown community or in
    `not_shown_nodes`; every community is shown or in `not_shown_clusters`."""
    overview = await _overview(_FakeGraph(), top=2)

    assert [c.id for c in overview.clusters] == ["comm-a", "comm-c"]
    # comm-z (3), comm-d (1) and the unlabelled e1 (its own community, 1) are not shown.
    assert overview.not_shown_clusters == 3
    assert overview.not_shown_nodes == 5
    assert overview.total_clusters == 5
    assert overview.total_nodes == 13
    assert overview.total_edges == 9
    assert sum(c.size for c in overview.clusters) + overview.not_shown_nodes == overview.total_nodes
    assert len(overview.clusters) + overview.not_shown_clusters == overview.total_clusters


async def test_a_node_the_algorithm_leaves_unlabelled_is_its_own_community_not_dropped() -> None:
    overview = await _overview(_FakeGraph(), top=10)

    assert sum(c.size for c in overview.clusters) == 13
    singleton = [c for c in overview.clusters if c.sample_node_ids == ["e1"]]
    assert len(singleton) == 1 and singleton[0].size == 1


async def test_a_node_the_principal_cannot_see_is_in_no_cluster_no_size_and_no_total() -> None:
    """`CLAUDE.md` rule 3: an unauthorised principal must not detect a filtered node's existence via
    a histogram bucket or a count. The overview for the restricted principal must be the overview of
    a graph that never had the hidden node."""
    hidden = _FakeGraph(hidden_from={RESTRICTED.id: {"a3"}})
    never_had_it = _FakeGraph(without={"a3"})

    seen_by_restricted = await _overview(hidden, RESTRICTED, top=10)
    seen_without_it = await _overview(never_had_it, FULL, top=10)

    assert seen_by_restricted == seen_without_it
    assert all("a3" not in c.sample_node_ids for c in seen_by_restricted.clusters)
    assert seen_by_restricted.total_nodes == 12


async def test_the_overview_never_carries_the_count_of_hidden_elements() -> None:
    overview = await _overview(_FakeGraph(hidden_from={RESTRICTED.id: {"a3"}}), RESTRICTED)

    assert "filtered" not in json.dumps(overview.model_dump(mode="json"))


async def test_a_second_call_from_the_same_access_class_is_served_from_the_cache() -> None:
    graph, cache, compute = _FakeGraph(), _FakeCache(), _FakeCompute()

    first = await _overview(graph, cache=cache, compute=compute)
    second = await _overview(graph, cache=cache, compute=compute)

    assert first == second
    assert len(graph.calls) == 1 and compute.calls == 1


async def test_a_different_access_class_is_never_served_anothers_cached_overview() -> None:
    """The cache key carries the principal's access class. A key built from the query alone would
    serve the restricted principal the full principal's overview, hidden node and all."""
    graph, cache = _FakeGraph(hidden_from={RESTRICTED.id: {"a3"}}), _FakeCache()

    full = await _overview(graph, FULL, cache=cache)
    restricted = await _overview(graph, RESTRICTED, cache=cache)

    assert len(graph.calls) == 2
    assert full.total_nodes == 13 and restricted.total_nodes == 12


async def test_a_graph_over_the_node_cap_is_a_typed_limit_exceeded_and_nothing_is_cached() -> None:
    cache = _FakeCache()

    with pytest.raises(LimitExceededError) as raised:
        await _overview(_FakeGraph(), cache=cache, max_nodes=5)

    assert raised.value.detail.error == "limit_exceeded"
    assert (raised.value.detail.cap_kind, raised.value.detail.cap) == ("nodes", 5)
    assert raised.value.detail.would_be == 13
    assert cache.puts == 0


async def test_a_graph_over_the_edge_cap_is_a_typed_limit_exceeded() -> None:
    with pytest.raises(LimitExceededError) as raised:
        await _overview(_FakeGraph(), max_edges=4)

    assert (raised.value.detail.cap_kind, raised.value.detail.cap) == ("edges", 4)
    assert raised.value.detail.would_be == 9


async def test_the_cap_breach_counts_only_what_the_principal_can_see() -> None:
    """Reporting 13 to a principal who can see 12 would disclose that a hidden node exists."""
    graph = _FakeGraph(hidden_from={RESTRICTED.id: {"a3"}})

    with pytest.raises(LimitExceededError) as raised:
        await _overview(graph, RESTRICTED, max_nodes=5)

    assert raised.value.detail.would_be == 12


async def test_the_caps_passed_to_the_store_are_the_working_sets() -> None:
    from services.api.working_set.models import MAX_EDGES, MAX_NODES

    graph = _FakeGraph()
    await _overview(graph)

    assert graph.calls[0][1:] == (MAX_NODES, MAX_EDGES)


async def test_a_store_that_returns_more_than_the_cap_is_still_a_typed_limit_exceeded() -> None:
    """Defence in depth: the port is meant to raise, but a store that hands back an over-cap
    subgraph must never reach the algorithm or the cache as a silent success."""

    class _Overfull(_FakeGraph):
        async def vault_subgraph(
            self, principal: Principal, *, max_nodes: int, max_edges: int
        ) -> Subgraph:
            return await super().vault_subgraph(principal, max_nodes=10**9, max_edges=10**9)

    cache = _FakeCache()
    with pytest.raises(LimitExceededError) as raised:
        await _overview(_Overfull(), cache=cache, max_nodes=5)

    assert (raised.value.detail.cap_kind, raised.value.detail.would_be) == ("nodes", 13)
    assert cache.puts == 0
