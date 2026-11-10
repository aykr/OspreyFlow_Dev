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
    """ADR-143 Amendment 5 decision 12 (the independent review of L3.4, item 4): the revert asks
    `live_edges_touching` inside its own transaction, so the read and the writes that follow are
    one view of the graph. A link written in that transaction, not yet committed, is seen through
    it; the same read outside it (a control, not the plant: the plant drops the session in the
    adapter's walk, `L3.4_RED_RECORD.md`'s d9436b4 section) does not see it. Rolled back, so
    nothing stays. The link goes to a third person: one between `loaded` and `drawn` would merge
    into `_drawn`'s own committed link (same pair, same type) and answer its id, seen everywhere
    (measured on ArcadeDB at d9436b4)."""
    async with factory.context() as adapter:
        _, drawn, _ = await _drawn(adapter)
        (third,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", datasets=[SOURCE])], []
        )
        held = await adapter.live_edges_touching([drawn])
        tx = await adapter.begin_transaction()
        try:
            (written,) = await adapter.upsert_edges(
                [_edge("ASSOCIATE_OF", drawn, third, classification="OFFICIAL",
                       datasets=[LAYER_A])],
                tx,
            )  # fmt: skip
            assert written not in held, "a new link, not a merge into a committed one"
            inside = await adapter.live_edges_touching([drawn], tx=tx)
            outside = await adapter.live_edges_touching([drawn])
        finally:
            await adapter.rollback_transaction(tx)
        assert written in inside
        assert written not in outside  # the control: a read without the session misses it
        assert written not in await adapter.live_edges_touching([drawn])


# --- a drawn dataset's merge (ADR-143 Amendment 2 decision 6; L3.9) --------------------------
#
# A merge is a promotion whose transaction also writes the chosen matches: a `SAME_AS` between a
# drawn node it promotes and a loaded node of the target, in the target alone. Both land together
# or neither does, and the revert withdraws the link with the load.


async def _merge(
    adapter: GraphPort, drawn: str, loaded: str, *, commit: bool = True
) -> str:
    tx = await adapter.begin_transaction()
    try:
        await adapter.promote_elements([drawn], [], SOURCE, LOAD, tx)
        (same,) = await adapter.upsert_edges(
            [_edge("SAME_AS", drawn, loaded, classification="OFFICIAL", datasets=[SOURCE])], tx
        )
    except Exception:
        await adapter.rollback_transaction(tx)
        raise
    if commit:
        await adapter.commit_transaction(tx)
    else:
        await adapter.rollback_transaction(tx)
    return same


async def test_a_merges_match_lands_with_its_promotion_and_its_revert_withdraws_it(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        loaded, drawn, _ = await _drawn(adapter)
        same = await _merge(adapter, drawn, loaded)
        assert await adapter.get_nodes([drawn], CASE_B)
        (link,) = await adapter.get_edges([same], CASE_B)
        assert (link.source, link.target, link.datasets) == (drawn, loaded, [SOURCE])

        tx = await adapter.begin_transaction()
        await adapter.revert_promotion(LOAD, SOURCE, tx)
        await adapter.withdraw_elements([], [same], LOAD, tx)
        await adapter.commit_transaction(tx)

        assert await adapter.get_nodes([drawn], CASE_B) == []
        assert await adapter.get_edges([same], CASE_B) == []
        assert await adapter.get_edges([same], EVERYONE) == []


async def test_a_merge_rolled_back_writes_neither_its_promotion_nor_its_match(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        loaded, drawn, _ = await _drawn(adapter)
        same = await _merge(adapter, drawn, loaded, commit=False)
        assert await adapter.get_nodes([drawn], CASE_B) == []
        assert await adapter.get_edges([same], EVERYONE) == []


async def test_the_together_check_fails_with_the_match_written_in_a_transaction_of_its_own(
    factory: GraphAdapterFactory,
) -> None:
    """The plant: the match committed on its own before the promotion, which then rolls back:
    the check above sees the link left behind."""
    async with factory.context() as adapter:
        loaded, drawn, _ = await _drawn(adapter)
        _, (same,) = await _write(
            adapter, [], [_edge("SAME_AS", drawn, loaded, classification="OFFICIAL",
                                datasets=[SOURCE])]
        )  # fmt: skip
        tx = await adapter.begin_transaction()
        await adapter.promote_elements([drawn], [], SOURCE, LOAD, tx)
        await adapter.rollback_transaction(tx)
        assert await adapter.get_edges([same], EVERYONE) != []


# --- a drawn merge's retyped copies (ADR-143 Amendment 7; L3.9) ----------------------------------
#
# A drawn item mapped onto another of the target's types is written by the merge's own load, in
# the promotion's transaction, as a new element of that type in the target; a link onto it is
# written in the same transaction, onto the copy not yet committed; the copy's `SAME_AS` back to its
# drawn original names no dataset (ADR-099 Amendment 2 decision 3: the two share none), so no
# reader of the target or of the drawing reads it, by id, among two nodes or by expanding; the
# revert reverts the copies as a load's own writes (`revert_elements`).

DRAWING = "drawn-dataset-1"
#: A reader of the target alone, and the drawing's home case after the merge (the target and the
#: drawing, read-only).
TARGET_READER = Principal(id="t", clearance="OFFICIAL", org_unit="unit-1", datasets=[SOURCE])
HOME_READER = Principal(
    id="h", clearance="OFFICIAL", org_unit="unit-1", datasets=[SOURCE, DRAWING]
)


async def _retyped(adapter: GraphPort, *, commit: bool = True) -> dict[str, str]:
    """A drawn incident and a drawn person in the drawing; the person promoted, the incident copied
    as an Organisation with a MEMBER_OF from the person onto the uncommitted copy, and the copy's
    SAME_AS back in no dataset: one transaction."""
    (incident, person), _ = await _write(
        adapter,
        [
            _node("Incident", classification="OFFICIAL", datasets=[DRAWING], name="Night fight"),
            _node("Person", classification="OFFICIAL", datasets=[DRAWING], family_name="Mercer"),
        ],
        [],
    )
    tx = await adapter.begin_transaction()
    try:
        await adapter.promote_elements([person], [], SOURCE, LOAD, tx)
        copy = _node("Organisation", classification="OFFICIAL", datasets=[SOURCE],
                     load_id=LOAD, name="Night fight")  # fmt: skip
        (copy_id,) = await adapter.upsert_nodes([copy], tx)
        member, back = await adapter.upsert_edges(
            [
                _edge("MEMBER_OF", person, copy_id, classification="OFFICIAL", datasets=[SOURCE],
                      load_id=LOAD),
                _edge("SAME_AS", copy_id, incident, classification="OFFICIAL", datasets=[],
                      load_id=LOAD),
            ],
            tx,
        )  # fmt: skip
    except Exception:
        await adapter.rollback_transaction(tx)
        raise
    if commit:
        await adapter.commit_transaction(tx)
    else:
        await adapter.rollback_transaction(tx)
    return {"incident": incident, "person": person, "copy": copy_id, "member": member,
            "back": back}  # fmt: skip


async def test_a_retyped_copy_and_a_link_onto_it_land_with_the_promotion_in_one_transaction(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _retyped(adapter)
        (copy,) = await adapter.get_nodes([ids["copy"]], TARGET_READER)
        assert (copy.type, copy.datasets, copy.properties.get("name")) == (
            "Organisation", [SOURCE], "Night fight",
        )  # fmt: skip
        (member,) = await adapter.get_edges([ids["member"]], TARGET_READER)
        assert (member.source, member.target) == (ids["person"], ids["copy"])
        # The original stays the drawing's alone, of its own type.
        (original,) = await adapter.get_nodes([ids["incident"]], HOME_READER)
        assert (original.type, original.datasets) == ("Incident", [DRAWING])


async def test_a_retyped_copy_rolled_back_writes_neither_it_nor_its_links(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _retyped(adapter, commit=False)
        assert await adapter.get_nodes([ids["copy"]], EVERYONE) == []
        assert await adapter.get_edges([ids["member"], ids["back"]], EVERYONE) == []


async def test_a_copys_same_as_back_names_no_dataset_and_no_reader_of_either_reads_it(
    factory: GraphAdapterFactory,
) -> None:
    """Read by id, among the two nodes and by expanding from either, as a reader of the target
    and as the drawing's home case: never there."""
    from schemas.domain import ExpandRequest

    async with factory.context() as adapter:
        ids = await _retyped(adapter)
        (stored,) = await adapter.get_edges([ids["back"]], EVERYONE)
        assert stored.datasets == []
        for reader in (TARGET_READER, HOME_READER):
            assert await adapter.get_edges([ids["back"]], reader) == []
            among = await adapter.edges_among([ids["copy"], ids["incident"]], reader)
            assert ids["back"] not in {e.id for e in among}
            for start in (ids["copy"], ids["incident"]):
                expanded = await adapter.expand(ExpandRequest(node_ids=[start]), reader)
                assert ids["back"] not in {e.id for e in expanded.edges}


async def test_reverting_the_copies_as_a_loads_own_writes_hides_them_from_every_reader(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _retyped(adapter)
        tx = await adapter.begin_transaction()
        await adapter.revert_promotion(LOAD, SOURCE, tx)
        await adapter.revert_elements([ids["copy"]], [ids["member"], ids["back"]], tx)
        await adapter.commit_transaction(tx)
        assert await adapter.get_nodes([ids["copy"]], EVERYONE) == []
        assert await adapter.get_edges([ids["member"], ids["back"]], EVERYONE) == []
        # The originals as they were: the person in the drawing alone again, the incident untouched.
        (person,) = await adapter.get_nodes([ids["person"]], HOME_READER)
        assert person.datasets == [DRAWING]
        assert await adapter.get_nodes([ids["incident"]], HOME_READER)


async def test_the_no_dataset_check_fails_with_the_back_link_put_in_the_drawing(
    factory: GraphAdapterFactory,
) -> None:
    """The plant: the `SAME_AS` back written into the drawing, as the merge first wrote it. The
    home case's reads above then find it among the two nodes and by expanding."""
    from schemas.domain import ExpandRequest

    async with factory.context() as adapter:
        (incident,), _ = await _write(
            adapter, [_node("Incident", classification="OFFICIAL", datasets=[DRAWING])], []
        )
        (copy,), _ = await _write(
            adapter, [_node("Organisation", classification="OFFICIAL", datasets=[SOURCE])], []
        )
        _, (back,) = await _write(
            adapter, [], [_edge("SAME_AS", copy, incident, classification="OFFICIAL",
                                datasets=[DRAWING])]
        )  # fmt: skip
        among = await adapter.edges_among([copy, incident], HOME_READER)
        assert back in {e.id for e in among}
        expanded = await adapter.expand(ExpandRequest(node_ids=[incident]), HOME_READER)
        assert back in {e.id for e in expanded.edges}
