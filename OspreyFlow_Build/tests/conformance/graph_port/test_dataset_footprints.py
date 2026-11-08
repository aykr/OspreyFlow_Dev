"""`GraphPort` conformance: `dataset_footprints`, the administrator's read of each case's analyst
layer as counts (`spec/06_DECISIONS.md` ADR-143 Amendment 2 decision 2; Admin › Datasets, L2.4
part 2). Written before the adapter's method (rule 1).

What a mistake would do, and the case that catches it:

- a layer's count taken from the wrong elements (another layer's, the source's, a reverted or a
  superseded one): `test_each_layer_is_counted_alone_and_only_its_live_elements`;
- the size not the bytes of the stored properties, or not growing with them:
  `test_the_size_is_the_stored_properties_bytes`;
- an id answered only when it holds something, so the answer says which ids exist:
  `test_every_id_asked_is_answered`;
- a picture's file not counted, or its object ref leaving the adapter:
  `test_a_picture_counts_its_stored_size_and_its_ref_never_leaves`;
- the read taking a principal (so a caller could filter it in the Conduit) or returning more than
  numbers: `test_it_takes_no_principal_and_returns_numbers_only`.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from ports.graph import DatasetFootprint, GraphPort, stored_properties_size
from schemas.domain import Principal
from tests.conformance.graph_port.test_suite import _edge, _node, _write
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

#: Each `factory.context()` is a fresh database, so these need not be unique per test.
SOURCE = "footprint-source"
LAYER_A = "footprint-layer-a"
LAYER_B = "footprint-layer-b"
NOTHING = "footprint-layer-empty"


def _each(test):  # type: ignore[no-untyped-def]
    """Against every adapter, after the sweep; the signature case below needs neither."""
    test = pytest.mark.usefixtures("_sweep_stale_conformance_databases")(test)
    return pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)(test)


@_each
async def test_each_layer_is_counted_alone_and_only_its_live_elements(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (loaded, _, _), _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL", datasets=[SOURCE]) for _ in range(3)],
            [],
        )
        (_, drawn_secret), _ = await _write_layer_a(adapter, loaded)
        await _write(adapter, [_node("Person", classification="OFFICIAL", datasets=[LAYER_B])], [])
        before = await adapter.dataset_footprints([LAYER_A, LAYER_B, SOURCE])
        assert (before[LAYER_A].nodes, before[LAYER_A].edges) == (2, 2)
        assert (before[LAYER_B].nodes, before[LAYER_B].edges) == (1, 0)
        assert (before[SOURCE].nodes, before[SOURCE].edges) == (3, 0)

        # A superseded node is no longer live; its replacement counts once in its place.
        tx = await adapter.begin_transaction()
        await adapter.supersede_node(
            drawn_secret, _node("Person", classification="SECRET", datasets=[LAYER_A]), tx
        )
        await adapter.commit_transaction(tx)
        after = await adapter.dataset_footprints([LAYER_A, LAYER_B])
        assert after[LAYER_A].nodes == 2
        assert after[LAYER_B] == before[LAYER_B]


async def _write_layer_a(adapter: GraphPort, loaded: str) -> tuple[list[str], list[str]]:
    """Two drawn people in layer A (one SECRET, above anyone's ordinary read: still one item in the
    count, decision 2), a link drawn between them and one from a loaded node, each in layer A
    alone."""
    first = _node("Person", classification="OFFICIAL", datasets=[LAYER_A])
    second = _node("Person", classification="SECRET", datasets=[LAYER_A])
    return await _write(
        adapter,
        [first, second],
        [
            _edge("KNOWS", first.id, second.id, classification="OFFICIAL", datasets=[LAYER_A]),
            _edge("KNOWS", loaded, first.id, classification="OFFICIAL", datasets=[LAYER_A]),
        ],
    )


@_each
async def test_the_size_is_the_stored_properties_bytes(factory: GraphAdapterFactory) -> None:
    short = _node("Person", classification="OFFICIAL", datasets=[LAYER_A], name="Al")
    long = _node("Person", classification="OFFICIAL", datasets=[LAYER_B], name="A" * 400)
    async with factory.context() as adapter:
        await _write(adapter, [short, long], [])
        sizes = await adapter.dataset_footprints([LAYER_A, LAYER_B])
    assert sizes[LAYER_A].properties_bytes == stored_properties_size(short.properties)
    assert sizes[LAYER_B].properties_bytes == stored_properties_size(long.properties)
    assert sizes[LAYER_B].properties_bytes - sizes[LAYER_A].properties_bytes == 398


@_each
async def test_every_id_asked_is_answered(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        found = await adapter.dataset_footprints([NOTHING, "never-made"])
        assert found == {NOTHING: DatasetFootprint(), "never-made": DatasetFootprint()}
        assert await adapter.dataset_footprints([]) == {}


def test_it_takes_no_principal_and_returns_numbers_only() -> None:
    """Infra-free: the port's own signature and the answer's shape."""
    parameters = inspect.signature(GraphPort.dataset_footprints).parameters
    assert list(parameters) == ["self", "dataset_ids"]
    assert all(p.annotation is not Principal for p in parameters.values())
    assert {f.name: f.type for f in dataclasses.fields(DatasetFootprint)} == {
        "nodes": "int",
        "edges": "int",
        "properties_bytes": "int",
        "picture_bytes": "int",
    }


#: The ref a picture's Document names its file by in the media store: never in the answer.
_REF = "picture-object-ref-0f3c9a"


@_each
async def test_a_picture_counts_its_stored_size_and_its_ref_never_leaves(
    factory: GraphAdapterFactory,
) -> None:
    """An image Document's `size_bytes` is summed as the layer's pictures; a text Document, or an
    image attached before the size was written, adds nothing. The answer holds only integers, and
    the object ref appears nowhere in it (shown red with the ref planted into the result)."""
    picture = _node(
        "Document", classification="OFFICIAL", datasets=[LAYER_A],
        title="Photo", media_kind="image", object_ref=_REF, size_bytes=5120,
    )  # fmt: skip
    older = _node(
        "Document", classification="OFFICIAL", datasets=[LAYER_A],
        title="Older photo", media_kind="image", object_ref=_REF + "-old",
    )  # fmt: skip
    text = _node(
        "Document", classification="OFFICIAL", datasets=[LAYER_A],
        title="Note", media_kind="text", size_bytes=999,
    )  # fmt: skip
    async with factory.context() as adapter:
        await _write(adapter, [picture, older, text], [])
        found = await adapter.dataset_footprints([LAYER_A])
    assert found[LAYER_A].picture_bytes == 5120
    assert found[LAYER_A].nodes == 3
    for counted in found.values():
        assert all(type(v) is int for v in dataclasses.astuple(counted)), counted
    assert _REF not in repr(found)
