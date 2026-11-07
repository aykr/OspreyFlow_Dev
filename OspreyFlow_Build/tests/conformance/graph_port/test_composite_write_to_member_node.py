"""`GraphPort` conformance, the lane-reviewer's finding 5 on L3.1 (ADR-099 Amendment 14): what a
case reading a composite writes is written under the composite's own id, so that "no case reading
only a member sees what the composite case added". This measures whether that holds when the
composite case writes to a node that is already in a member.

The real call site's shape: the stamping graph gives a write naming no dataset the case's first,
the composite's id; the write names the existing node's id (a correction made in the case, an
ingest row that matches it), with one property changed; and a new link between two member nodes.

Written first and run before anything was changed, at the owner's ruling (7 November 2026): the
owner decides what should happen after seeing what this shows. Until then each case is
`xfail(strict=True)`, so the suite stays green and a change in the adapter's behaviour turns it red.
"""

from __future__ import annotations

import pytest

from ports.graph import GraphPort
from schemas.domain import Principal
from tests.conformance.graph_port.test_suite import _edge, _node, _write
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = [
    pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str),
    pytest.mark.usefixtures("_sweep_stale_conformance_databases"),
]

MEMBER = "member-dataset"
OTHER_MEMBER = "other-member-dataset"
COMPOSITE = "composite-dataset"

#: Read sets as `DatasetStore.ids_of_case` builds them (the composite's own id first).
COMPOSITE_CASE = Principal(
    id="analyst-c",
    clearance="OFFICIAL",
    org_unit="unit-1",
    datasets=[COMPOSITE, MEMBER, OTHER_MEMBER, "layer-c"],
)
MEMBER_CASE = Principal(
    id="analyst-m", clearance="OFFICIAL", org_unit="unit-1", datasets=[MEMBER, "layer-m"]
)

PENDING = pytest.mark.xfail(
    strict=True,
    reason="finding 5: the adapter merges a write into the existing element; owner to decide",
)


async def _loaded(adapter: GraphPort) -> tuple[str, str]:
    (a, b), _ = await _write(
        adapter,
        [
            _node("Person", classification="OFFICIAL", datasets=[MEMBER], family_name="MERCER"),
            _node("Person", classification="OFFICIAL", datasets=[MEMBER], family_name="PRICE"),
        ],
        [],
    )
    return a, b


@PENDING
async def test_a_composite_cases_write_to_a_member_node_leaves_it_unchanged_for_a_member_case(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        a, _b = await _loaded(adapter)
        before = await adapter.get_node(a, MEMBER_CASE)
        assert before is not None and before.properties["family_name"] == "MERCER"

        rewrite = _node(
            "Person", classification="OFFICIAL", datasets=[COMPOSITE], family_name="MERCER-JONES"
        ).model_copy(update={"id": a})
        await _write(adapter, [rewrite], [])

        # The control: the composite case reads its write.
        in_composite = await adapter.get_node(a, COMPOSITE_CASE)
        assert in_composite is not None
        assert in_composite.properties["family_name"] == "MERCER-JONES"

        after = await adapter.get_node(a, MEMBER_CASE)
        assert after is not None
        assert after.properties == before.properties
        assert after.datasets == before.datasets


async def test_a_composite_cases_link_between_member_nodes_is_not_seen_by_a_member_case(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        a, b = await _loaded(adapter)
        before = await adapter.neighbourhood_stats(a, MEMBER_CASE)
        await _write(
            adapter,
            [],
            [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL", datasets=[COMPOSITE])],
        )
        assert (await adapter.neighbourhood_stats(a, COMPOSITE_CASE)).degree == before.degree + 1
        assert (await adapter.neighbourhood_stats(a, MEMBER_CASE)).degree == before.degree
        assert await adapter.edges_among([a, b], MEMBER_CASE) == []
