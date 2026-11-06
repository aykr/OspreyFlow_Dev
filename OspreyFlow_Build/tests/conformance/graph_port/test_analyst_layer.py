"""`GraphPort` conformance: a case's analyst layer is invisible from every other case, including by
inference (`spec/06_DECISIONS.md` ADR-143 decisions 1 and 3; `spec/04_VAULT_BACKEND.md` §6).

Case A and case B read the same source dataset; each owns its own analyst layer. Links drawn in
A's layer from a loaded node (to a drawn node, and between two loaded nodes) must leave everything
case B can measure about that loaded node exactly as it was before they were written: its degree,
its degree by link type (the bucket a histogram of the neighbourhood is drawn from), its rank and
degree in the most-connected list, the type counts, its `expand` neighbourhood, whether and at
what length a path reaches another loaded node, and the links `edges_among` finds between the two.

Nothing here is new machinery: the layer is a dataset like any other, filtered by
`Principal.datasets` in the one access step (`AccessFilter.gremlin_has_step`). That is the point:
the test fails if the read set or the access step ever lets a layer through.

**Shown red (rule 15).** `test_the_case_b_check_fails_with_case_a_layer_in_case_b_read_set`
plants the real call site's shape of the defect (case A's layer id in case B's
`Principal.datasets`, which is exactly what a wrong read set would produce) and asserts the
measurements now differ. If it ever passes with the plant removed, the main test could not have
found the leak.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ports.graph import GraphPort
from schemas.domain import ExpandRequest, PathRequest, Principal
from tests.conformance.graph_port.test_suite import _edge, _node, _write
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = [
    pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str),
    pytest.mark.usefixtures("_sweep_stale_conformance_databases"),
]

SOURCE = "source-dataset"
LAYER_A = "analyst-layer-case-a"
LAYER_B = "analyst-layer-case-b"

#: The read sets the Conduit builds for a request under each case (ADR-143 decision 1).
CASE_A = Principal(
    id="analyst-a", clearance="OFFICIAL", org_unit="unit-1", datasets=[SOURCE, LAYER_A]
)
CASE_B = Principal(
    id="analyst-b", clearance="OFFICIAL", org_unit="unit-1", datasets=[SOURCE, LAYER_B]
)


@dataclass(frozen=True)
class _Seen:
    """Everything a reader can measure about the loaded node `hub`."""

    degree: int
    degree_by_type: dict[str, int]
    ranked_degree: int | None
    ranked_total: int
    node_counts: dict[str, int]
    edge_counts: dict[str, int]
    expanded: frozenset[str]
    path_lengths: tuple[int, ...]
    #: The links among what is on screen (ADR-098): the drawn hub-to-far link is one.
    among: int


async def _measure(adapter: GraphPort, hub: str, far: str, reader: Principal) -> _Seen:
    stats = await adapter.neighbourhood_stats(hub, reader)
    ranked = await adapter.most_connected(reader, limit=50)
    counts = await adapter.type_counts(reader)
    expanded = await adapter.expand(ExpandRequest(node_ids=[hub], depth=2), reader)
    paths = await adapter.paths(PathRequest(source=hub, target=far, max_hops=4, k=5), reader)
    among = await adapter.edges_among([hub, far], reader)
    return _Seen(
        degree=stats.degree,
        degree_by_type=dict(stats.degree_by_type),
        ranked_degree=next((n.degree for n in ranked.nodes if n.node.id == hub), None),
        ranked_total=ranked.total,
        node_counts=dict(counts.nodes),
        edge_counts=dict(counts.edges),
        expanded=frozenset(n.id for n in expanded.nodes),
        path_lengths=tuple(sorted(p.length for p in paths)),
        among=len(among),
    )


async def _loaded(adapter: GraphPort) -> tuple[str, str, str]:
    """Three loaded people in the source dataset: `hub` knows `near`; `far` is linked to nothing
    case B can see, so B has no path from `hub` to `far`."""
    (hub, near, far), _ = await _write(
        adapter,
        [_node("Person", classification="OFFICIAL", datasets=[SOURCE]) for _ in range(3)],
        [],
    )
    await _write(
        adapter,
        [],
        [_edge("ASSOCIATE_OF", hub, near, classification="OFFICIAL", datasets=[SOURCE])],
    )
    return hub, near, far


async def _draw_in_case_a(adapter: GraphPort, hub: str, far: str) -> None:
    """What an analyst of case A draws: a declared node linked from the loaded `hub`, and a link
    from `hub` to the loaded `far`. Both links, and the drawn node, live in A's layer; the loaded
    nodes stay in the source dataset untouched (ADR-143 decision 2)."""
    (drawn,), _ = await _write(
        adapter, [_node("Person", classification="OFFICIAL", datasets=[LAYER_A])], []
    )
    await _write(
        adapter,
        [],
        [
            _edge("ASSOCIATE_OF", hub, drawn, classification="OFFICIAL", datasets=[LAYER_A]),
            _edge("ASSOCIATE_OF", hub, far, classification="OFFICIAL", datasets=[LAYER_A]),
        ],
    )


async def test_a_link_in_case_as_layer_leaves_the_loaded_node_unchanged_under_case_b(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        hub, _near, far = await _loaded(adapter)
        before = await _measure(adapter, hub, far, CASE_B)
        await _draw_in_case_a(adapter, hub, far)
        after = await _measure(adapter, hub, far, CASE_B)

        assert after == before
        assert before.path_lengths == ()  # B has no route to `far` at all
        # The control: the drawing did land, and case A reads it (else "unchanged" is trivial).
        in_a = await _measure(adapter, hub, far, CASE_A)
        assert in_a.degree == before.degree + 2
        assert in_a.path_lengths[:1] == (1,)


async def test_the_case_b_check_fails_with_case_a_layer_in_case_b_read_set(
    factory: GraphAdapterFactory,
) -> None:
    """The red half (rule 15): the defect planted in the shape a wrong read set takes."""
    leaky_b = CASE_B.model_copy(update={"datasets": [SOURCE, LAYER_B, LAYER_A]})
    async with factory.context() as adapter:
        hub, _near, far = await _loaded(adapter)
        before = await _measure(adapter, hub, far, leaky_b)
        await _draw_in_case_a(adapter, hub, far)
        after = await _measure(adapter, hub, far, leaky_b)

        assert after != before
        assert after.degree != before.degree
        assert after.degree_by_type != before.degree_by_type
        assert after.ranked_degree != before.ranked_degree
        assert after.edge_counts != before.edge_counts
        assert after.expanded != before.expanded
        assert after.path_lengths != before.path_lengths
        assert after.among != before.among
