"""`GraphPort` conformance: a promotion is one load that adds a dataset to the drawn elements
themselves, and a removed case's layer is withdrawn without touching what was promoted from it
(`spec/06_DECISIONS.md` ADR-143 decision 8; Amendment 2 decision 1; L3.4).

Case A and case B read the same source dataset. A draws a person in its layer and links it to a
loaded person. Promoting the two into the source makes them readable from case B: as the same
element, whose `datasets` holds the layer and the source (ADR-099 decision 2's union), never a
copy (rule 6). The promotion is all or nothing. Its revert leaves the elements in A's layer only.
Withdrawing A's layer takes away what was never promoted and leaves what was.

**Shown red (rule 15).** Each check is an assertion over what case B reads, and each has a plant in
the shape the real defect would take at the call site:
`test_the_one_element_check_fails_with_the_promotion_written_as_a_copy` writes the promotion the way
an upsert into the source would (a new node), and asserts the check sees two;
`test_the_all_or_nothing_check_fails_with_the_all_live_check_removed` replaces the adapter's own
all-live check with one that refuses nothing, and asserts the live elements land beside a withdrawn
one.
"""

from __future__ import annotations

import pytest

from ports.graph import GraphPort, NotPromotable
from schemas.domain import Principal
from tests.conformance.graph_port.test_suite import _edge, _node, _write
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = [
    pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str),
    pytest.mark.usefixtures("_sweep_stale_conformance_databases"),
]

SOURCE = "source-dataset"
LAYER_A = "analyst-layer-case-a"
LAYER_B = "analyst-layer-case-b"
CASE_A = Principal(id="a", clearance="OFFICIAL", org_unit="unit-1", datasets=[SOURCE, LAYER_A])
CASE_B = Principal(id="b", clearance="OFFICIAL", org_unit="unit-1", datasets=[SOURCE, LAYER_B])
#: Every dataset: to count what the store holds, whoever drew it.
EVERYONE = Principal(id="all", clearance="OFFICIAL", org_unit="unit-1", datasets=None)
LOAD = "promotion-load-1"


async def _drawn(adapter: GraphPort) -> tuple[str, str, str]:
    """A loaded person in the source; a drawn person in A's layer; a drawn link between them."""
    (loaded,), _ = await _write(
        adapter, [_node("Person", classification="OFFICIAL", datasets=[SOURCE])], []
    )
    (drawn,), _ = await _write(
        adapter,
        [_node("Person", classification="OFFICIAL", datasets=[LAYER_A], family_name="Tall")],
        [],
    )
    _, (link,) = await _write(
        adapter,
        [],
        [_edge("ASSOCIATE_OF", loaded, drawn, classification="OFFICIAL", datasets=[LAYER_A])],
    )
    return loaded, drawn, link


async def _promote(adapter: GraphPort, nodes: list[str], links: list[str]) -> None:
    tx = await adapter.begin_transaction()
    try:
        await adapter.promote_elements(nodes, links, SOURCE, LOAD, tx)
    except Exception:
        await adapter.rollback_transaction(tx)
        raise
    await adapter.commit_transaction(tx)


async def _people(adapter: GraphPort) -> int:
    return (await adapter.type_counts(EVERYONE)).nodes.get("Person", 0)


async def _b_reads(adapter: GraphPort, drawn: str, link: str) -> tuple[bool, bool]:
    nodes = await adapter.get_nodes([drawn], CASE_B)
    edges = await adapter.get_edges([link], CASE_B)
    return bool(nodes), bool(edges)


async def _promoted_as_one(adapter: GraphPort, drawn: str, people_before: int) -> bool:
    """The check: case B reads the drawn element itself, holding both datasets, and the store
    holds no more people than before (no copy)."""
    seen = await adapter.get_nodes([drawn], CASE_B)
    return (
        len(seen) == 1
        and sorted(seen[0].datasets) == sorted([LAYER_A, SOURCE])
        and await _people(adapter) == people_before
    )


async def test_a_promotion_adds_the_dataset_to_the_drawn_elements_themselves(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        _, drawn, link = await _drawn(adapter)
        assert await _b_reads(adapter, drawn, link) == (False, False)
        people = await _people(adapter)

        await _promote(adapter, [drawn], [link])

        assert await _promoted_as_one(adapter, drawn, people)
        assert await _b_reads(adapter, drawn, link) == (True, True)
        (edge,) = await adapter.get_edges([link], CASE_B)
        assert sorted(edge.datasets) == sorted([LAYER_A, SOURCE])
        # Its marking and provenance are as drawn: nothing else of it changes.
        (before,) = await adapter.get_nodes([drawn], CASE_A)
        assert before.handling.classification == "OFFICIAL"
        assert before.properties.get("family_name") == "Tall"


async def test_the_one_element_check_fails_with_the_promotion_written_as_a_copy(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        _, drawn, _ = await _drawn(adapter)
        people = await _people(adapter)
        # The plant: the promotion as an upsert into the source would write it, a new node.
        await _write(
            adapter,
            [_node("Person", classification="OFFICIAL", datasets=[SOURCE], family_name="Tall")],
            [],
        )
        assert not await _promoted_as_one(adapter, drawn, people)


async def _withdrawn(adapter: GraphPort) -> str:
    (gone,), _ = await _write(
        adapter, [_node("Person", classification="OFFICIAL", datasets=[LAYER_A])], []
    )
    tx = await adapter.begin_transaction()
    await adapter.withdraw_elements([gone], [], "board-withdrawal:x", tx)
    await adapter.commit_transaction(tx)
    return gone


async def _superseded(adapter: GraphPort) -> str:
    """A drawn node replaced by a correction: the old revision is not live."""
    old = _node("Person", classification="OFFICIAL", datasets=[LAYER_A], family_name="Old")
    (old_id,), _ = await _write(adapter, [old], [])
    tx = await adapter.begin_transaction()
    await adapter.supersede_node(
        old_id, _node("Person", classification="OFFICIAL", datasets=[LAYER_A]), tx
    )
    await adapter.commit_transaction(tx)
    return old_id


async def test_a_promotion_with_a_withdrawn_element_writes_nothing(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        _, drawn, link = await _drawn(adapter)
        gone = await _withdrawn(adapter)
        with pytest.raises(NotPromotable):
            await _promote(adapter, [drawn, gone], [link])
        assert await _b_reads(adapter, drawn, link) == (False, False)


async def test_a_promotion_with_a_superseded_element_writes_nothing(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        _, drawn, link = await _drawn(adapter)
        old = await _superseded(adapter)
        with pytest.raises(NotPromotable):
            await _promote(adapter, [drawn, old], [link])
        assert await _b_reads(adapter, drawn, link) == (False, False)


async def test_an_element_promoted_by_another_load_is_not_promoted_again(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        _, drawn, link = await _drawn(adapter)
        await _promote(adapter, [drawn], [])
        tx = await adapter.begin_transaction()
        with pytest.raises(NotPromotable):
            await adapter.promote_elements([drawn], [link], SOURCE, "promotion-load-2", tx)
        await adapter.rollback_transaction(tx)
        # The first load's revert still takes back what it promoted.
        tx = await adapter.begin_transaction()
        taken = await adapter.revert_promotion(LOAD, SOURCE, tx)
        await adapter.commit_transaction(tx)
        assert (taken.nodes, taken.edges) == (1, 0)
        assert await _b_reads(adapter, drawn, link) == (False, False)


async def test_the_all_or_nothing_check_fails_with_the_all_live_check_removed(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with factory.context() as adapter:
        _, drawn, link = await _drawn(adapter)
        gone = await _withdrawn(adapter)
        # The plant, at the adapter's own call site: the all-live check made to refuse nothing,
        # so the live elements are written and the withdrawn one skipped.
        monkeypatch.setattr(
            type(adapter), "_refuse_unless_all_live", staticmethod(lambda wanted, live: None)
        )
        await _promote(adapter, [drawn, gone], [link])
        assert await _b_reads(adapter, drawn, link) != (False, False)


async def test_reverting_a_promotion_leaves_the_elements_in_the_layer_only(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        _, drawn, link = await _drawn(adapter)
        await _promote(adapter, [drawn], [link])

        tx = await adapter.begin_transaction()
        taken = await adapter.revert_promotion(LOAD, SOURCE, tx)
        await adapter.commit_transaction(tx)

        assert (taken.nodes, taken.edges) == (1, 1)
        assert await _b_reads(adapter, drawn, link) == (False, False)
        (held,) = await adapter.get_nodes([drawn], CASE_A)
        assert held.datasets == [LAYER_A]
        (edge,) = await adapter.get_edges([link], CASE_A)
        assert edge.datasets == [LAYER_A]
        tx = await adapter.begin_transaction()
        again = await adapter.revert_promotion(LOAD, SOURCE, tx)
        await adapter.commit_transaction(tx)
        assert (again.nodes, again.edges) == (0, 0)


async def test_withdrawing_a_layer_leaves_what_was_promoted_from_it(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        loaded, drawn, link = await _drawn(adapter)
        (kept_back,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", datasets=[LAYER_A])], []
        )
        _, (kept_link,) = await _write(
            adapter,
            [],
            [_edge("ASSOCIATE_OF", loaded, kept_back, classification="OFFICIAL", datasets=[LAYER_A])],
        )
        await _promote(adapter, [drawn], [link])

        tx = await adapter.begin_transaction()
        gone = await adapter.withdraw_layer(LAYER_A, "layer-delete:case-a", tx)
        await adapter.commit_transaction(tx)

        assert (gone.nodes, gone.edges) == (1, 1)
        assert not await adapter.get_nodes([kept_back], CASE_A)
        assert not await adapter.get_edges([kept_link], CASE_A)
        assert await _b_reads(adapter, drawn, link) == (True, True)
        assert await adapter.get_nodes([loaded], CASE_B)


async def test_the_resting_link_read_inside_a_transaction_sees_what_it_wrote(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-143 Amendment 5 decision 8 (the independent review of L3.4, item 4): the revert asks
    `live_edges_touching` inside its own transaction, so the read and the writes that follow are
    one view of the graph. A link written in that transaction, not yet committed, is seen through
    it; the same read outside it (the plant: the session dropped) does not see it. Rolled back, so
    nothing stays."""
    async with factory.context() as adapter:
        loaded, drawn, _ = await _drawn(adapter)
        tx = await adapter.begin_transaction()
        try:
            (written,) = await adapter.upsert_edges(
                [_edge("ASSOCIATE_OF", loaded, drawn, classification="OFFICIAL",
                       datasets=[LAYER_A])],
                tx,
            )  # fmt: skip
            inside = await adapter.live_edges_touching([drawn], tx=tx)
            outside = await adapter.live_edges_touching([drawn])
        finally:
            await adapter.rollback_transaction(tx)
        assert written in inside
        assert written not in outside  # the plant: a read without the session misses it
        assert written not in await adapter.live_edges_touching([drawn])
