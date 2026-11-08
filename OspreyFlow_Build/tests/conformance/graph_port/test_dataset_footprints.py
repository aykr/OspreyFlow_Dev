"""`GraphPort` conformance: `dataset_footprints`, an administrator's read of each case's analyst
layer as counts (`spec/06_DECISIONS.md` ADR-143 Amendment 2 decision 2; Admin › Datasets, L2.4
part 2). Decision 2 lifts case membership for Admin, never handling (ADR-124 decision 10): the
count is of what the reader may read, through the access step every read uses. Written before the
adapter's method (rule 1; the red run is in `process/lanes/admin/L2.4p2_RED_RECORD.md`).

What a mistake would do, and the case that catches it:

- a SECRET item counted, or its size added, for a reader below SECRET; a restricted code's item
  counted for a reader outside its unit; a link counted whose end the reader cannot read:
  `test_what_the_reader_may_not_read_is_in_no_count_and_no_size`;
- a link counted whose own marking or code the reader may not read, its ends readable:
  `test_a_links_own_handling_is_held`;
- another layer's or the source's elements counted: `test_each_layer_is_counted_alone`;
- a reverted element counted, a superseded node counted beside its replacement, or the links
  `supersede_node` clones counted twice: `test_only_live_elements_count_and_cloned_links_once`;
- the size not growing with the stored properties: `test_the_size_grows_with_the_stored_properties`;
- a picture's file not counted, or its object ref leaving the store:
  `test_a_picture_counts_its_stored_size_and_its_ref_never_leaves`;
- an id answered only when it holds something: `test_every_id_asked_is_answered`;
- the read taking no reader, or answering more than numbers:
  `test_it_takes_the_reader_and_returns_numbers_only`.
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import Any

import pytest

from ports.graph import DatasetFootprint, GraphPort
from schemas.domain import NodeWrite, Principal
from tests.conformance.graph_port.test_suite import _edge, _node, _write
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

#: Each `factory.context()` is a fresh database, so these need not be unique per test.
SOURCE = "footprint-source"
LAYER_A = "footprint-layer-a"
LAYER_B = "footprint-layer-b"
NOTHING = "footprint-layer-empty"

#: Administrators, members of no case: one cleared to SECRET who may receive `R` in its unit, one
#: cleared to OFFICIAL, and one who may receive `R` but sits in another unit.
SECRET_ADMIN = Principal(
    id="adm-s", clearance="SECRET", org_unit="unit-1", receivable_handling_codes=["R"]
)
OFFICIAL_ADMIN = Principal(id="adm-o", clearance="OFFICIAL", org_unit="unit-1")
ELSEWHERE_ADMIN = Principal(
    id="adm-e", clearance="SECRET", org_unit="unit-elsewhere", receivable_handling_codes=["R"]
)


def _each(test: Any) -> Any:
    """Against every adapter, after the sweep; the signature case below needs neither."""
    test = pytest.mark.usefixtures("_sweep_stale_conformance_databases")(test)
    return pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)(test)


def _person(dataset: str, classification: str = "OFFICIAL", **kwargs: Any) -> NodeWrite:
    return _node("Person", classification=classification, datasets=[dataset], **kwargs)


def _link(source: str, target: str) -> Any:
    return _edge("ASSOCIATE_OF", source, target, classification="OFFICIAL", datasets=[LAYER_A])


@_each
async def test_what_the_reader_may_not_read_is_in_no_count_and_no_size(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (plain,), _ = await _write(adapter, [_person(LAYER_A, given_names="Plain")], [])
        baseline = (await adapter.dataset_footprints([LAYER_A], OFFICIAL_ADMIN))[LAYER_A]
        secret = _person(LAYER_A, "SECRET", given_names="S" * 300)
        restricted = _node(
            "Person", classification="OFFICIAL", handling_code="R", datasets=[LAYER_A],
            given_names="R" * 300,
        )  # fmt: skip
        await _write(adapter, [secret, restricted], [_link(plain, secret.id)])
        official = (await adapter.dataset_footprints([LAYER_A], OFFICIAL_ADMIN))[LAYER_A]
        elsewhere = (await adapter.dataset_footprints([LAYER_A], ELSEWHERE_ADMIN))[LAYER_A]
        cleared = (await adapter.dataset_footprints([LAYER_A], SECRET_ADMIN))[LAYER_A]
    # Below SECRET: neither the SECRET item, nor the link to it, nor the restricted item's size.
    assert official == baseline
    assert (official.nodes, official.edges) == (1, 0)
    # Cleared, but outside the restricted code's unit: the SECRET item and its link, not the `R`.
    assert (elsewhere.nodes, elsewhere.edges) == (2, 1)
    assert (cleared.nodes, cleared.edges) == (3, 1)
    assert cleared.properties_bytes - elsewhere.properties_bytes >= 300


@_each
async def test_a_links_own_handling_is_held(factory: GraphAdapterFactory) -> None:
    """Both ends readable to every reader below; the links themselves are SECRET and `R`."""
    async with factory.context() as adapter:
        (one, two), _ = await _write(adapter, [_person(LAYER_A), _person(LAYER_A)], [])
        baseline = (await adapter.dataset_footprints([LAYER_A], OFFICIAL_ADMIN))[LAYER_A]
        await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", one, two, classification="SECRET", datasets=[LAYER_A]),
                _edge("ASSOCIATE_OF", two, one, classification="OFFICIAL", handling_code="R",
                      datasets=[LAYER_A]),
            ],
        )  # fmt: skip
        official = (await adapter.dataset_footprints([LAYER_A], OFFICIAL_ADMIN))[LAYER_A]
        elsewhere = (await adapter.dataset_footprints([LAYER_A], ELSEWHERE_ADMIN))[LAYER_A]
        cleared = (await adapter.dataset_footprints([LAYER_A], SECRET_ADMIN))[LAYER_A]
    assert official == baseline and official.edges == 0
    assert elsewhere.edges == 1 and elsewhere.properties_bytes > baseline.properties_bytes
    assert cleared.edges == 2 and cleared.properties_bytes > elsewhere.properties_bytes


@_each
async def test_each_layer_is_counted_alone(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        (loaded, _, _), _ = await _write(adapter, [_person(SOURCE) for _ in range(3)], [])
        (first, second), _ = await _write(adapter, [_person(LAYER_A), _person(LAYER_A)], [])
        await _write(adapter, [_person(LAYER_B)], [_link(first, second), _link(loaded, first)])
        found = await adapter.dataset_footprints([LAYER_A, LAYER_B, SOURCE], SECRET_ADMIN)
    assert (found[LAYER_A].nodes, found[LAYER_A].edges) == (2, 2)
    assert (found[LAYER_B].nodes, found[LAYER_B].edges) == (1, 0)
    assert (found[SOURCE].nodes, found[SOURCE].edges) == (3, 0)


@_each
async def test_only_live_elements_count_and_cloned_links_once(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (loaded,), _ = await _write(adapter, [_person(SOURCE)], [])
        drawn, gone = _person(LAYER_A), _person(LAYER_A)
        _, (_, gone_link) = await _write(
            adapter, [drawn, gone], [_link(loaded, drawn.id), _link(loaded, gone.id)]
        )
        before = (await adapter.dataset_footprints([LAYER_A], SECRET_ADMIN))[LAYER_A]
        assert (before.nodes, before.edges) == (2, 2)
        # Superseded: the replacement counts in its place, and the link `supersede_node` clones
        # onto it counts once, its superseded original not at all.
        tx = await adapter.begin_transaction()
        await adapter.supersede_node(drawn.id, _person(LAYER_A, given_names="Corrected"), tx)
        await adapter.commit_transaction(tx)
        corrected = (await adapter.dataset_footprints([LAYER_A], SECRET_ADMIN))[LAYER_A]
        assert (corrected.nodes, corrected.edges) == (2, 2)
        # Reverted: in no count.
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([gone.id], [gone_link], tx)
        await adapter.commit_transaction(tx)
        reverted = (await adapter.dataset_footprints([LAYER_A], SECRET_ADMIN))[LAYER_A]
        assert (reverted.nodes, reverted.edges) == (1, 1)


@_each
async def test_the_size_grows_with_the_stored_properties(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        await _write(
            adapter,
            [_person(LAYER_A, given_names="Al"), _person(LAYER_B, given_names="A" * 400)],
            [],
        )
        sizes = await adapter.dataset_footprints([LAYER_A, LAYER_B], SECRET_ADMIN)
    assert sizes[LAYER_A].properties_bytes > 0
    assert sizes[LAYER_B].properties_bytes - sizes[LAYER_A].properties_bytes == 398


#: The ref a picture's Document names its file by in the media store: never in the answer.
_REF = "picture-object-ref-0f3c9a"


@_each
async def test_a_picture_counts_its_stored_size_and_its_ref_never_leaves(
    factory: GraphAdapterFactory,
) -> None:
    """An image Document's `size_bytes` is summed as the layer's pictures; a text Document, or an
    image attached before the size was written, adds nothing. The answer holds only integers, and
    the object ref appears nowhere in it."""
    documents = [
        _node("Document", classification="OFFICIAL", datasets=[LAYER_A], title="Photo",
              media_kind="image", object_ref=_REF, size_bytes=5120),
        _node("Document", classification="OFFICIAL", datasets=[LAYER_A], title="Older photo",
              media_kind="image", object_ref=_REF + "-old"),
        _node("Document", classification="OFFICIAL", datasets=[LAYER_A], title="Note",
              media_kind="text", size_bytes=999),
    ]  # fmt: skip
    async with factory.context() as adapter:
        await _write(adapter, documents, [])
        found = await adapter.dataset_footprints([LAYER_A], SECRET_ADMIN)
    assert found[LAYER_A].picture_bytes == 5120
    assert found[LAYER_A].nodes == 3
    for counted in found.values():
        assert all(type(v) is int for v in dataclasses.astuple(counted)), counted
    assert _REF not in repr(found)


@_each
async def test_every_id_asked_is_answered(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        found = await adapter.dataset_footprints([NOTHING, "never-made"], SECRET_ADMIN)
        assert found == {NOTHING: DatasetFootprint(), "never-made": DatasetFootprint()}
        assert await adapter.dataset_footprints([], SECRET_ADMIN) == {}


def test_it_takes_the_reader_and_returns_numbers_only() -> None:
    """Infra-free: the port's own signature and the answer's shape."""
    parameters = inspect.signature(GraphPort.dataset_footprints).parameters
    assert list(parameters) == ["self", "dataset_ids", "principal"]
    assert {f.name: f.type for f in dataclasses.fields(DatasetFootprint)} == {
        "nodes": "int",
        "edges": "int",
        "properties_bytes": "int",
        "picture_bytes": "int",
    }
