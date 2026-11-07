"""`GraphPort` conformance for a case reading a composite (ADR-099 Amendments 14 and 15): a
composite is read-only for now (the owner's ruling, 7 November 2026). The lane-reviewer's finding
5 on L3.1 measured that a composite case's write naming a node already in a member was merged
into it, so a case reading only the member saw the change. Now every write in a composite case,
other than into the case's own analyst layer, is refused before it reaches the store, and no
member changes.

Driven through the Conduit's own write path, the stamping graph, with the request's case in scope as
`scope_to_case` holds it, over the real adapter. Shown red (rule 15) with the stamping graph's
refusal planted out, when the member's node changes again.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.dataset_scope import (
    CompositeReadOnlyError,
    DatasetStampingGraph,
    set_case_datasets,
    stamping,
)
from services.api.datasets import ANALYST_LAYER, Dataset, InMemoryDatasetStore

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
LAYER = "layer-c"

#: Read sets as `DatasetStore.ids_of_case` builds them (the composite's own id first).
COMPOSITE_CASE = Principal(
    id="analyst-c",
    clearance="OFFICIAL",
    org_unit="unit-1",
    datasets=[COMPOSITE, MEMBER, OTHER_MEMBER, LAYER],
)
MEMBER_CASE = Principal(
    id="analyst-m", clearance="OFFICIAL", org_unit="unit-1", datasets=[MEMBER, "layer-m"]
)


def _dataset(dataset_id: str, **kind: object) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=dataset_id,
        owning_unit="unit-1",
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        created_by="seed",
        **kind,  # type: ignore[arg-type]
    )


def _in_the_composite_case(adapter: GraphPort) -> GraphPort:
    """The stamping graph over `adapter`, with a request scoped to the composite case."""
    store = InMemoryDatasetStore()
    for dataset_id in (MEMBER, OTHER_MEMBER):
        store.add(_dataset(dataset_id))
    store.add(_dataset(COMPOSITE, kind="composite", members=[MEMBER, OTHER_MEMBER]))
    store.add(_dataset(LAYER, kind=ANALYST_LAYER, layer_of="case-c"))
    store.cases["case-c"] = [COMPOSITE]
    set_case_datasets(COMPOSITE_CASE.datasets, layer=LAYER, scope=("case-c", store, COMPOSITE_CASE))
    return stamping(adapter, registry=store)  # type: ignore[return-value]


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


async def _rewrite(adapter: GraphPort, a: str) -> None:
    """The composite case's write naming the member's node `a`, one property changed, naming no
    dataset as a writer under a case leaves it."""
    graph = _in_the_composite_case(adapter)
    rewrite = _node("Person", classification="OFFICIAL", family_name="MERCER-JONES").model_copy(
        update={"id": a, "datasets": []}
    )
    try:
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([rewrite], tx)
        await graph.commit_transaction(tx)
    finally:
        set_case_datasets(None)


async def test_a_composite_cases_write_to_a_member_node_is_refused_and_the_member_unchanged(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        a, _b = await _loaded(adapter)
        before = await adapter.get_node(a, MEMBER_CASE)
        with pytest.raises(CompositeReadOnlyError):
            await _rewrite(adapter, a)
        assert await adapter.get_node(a, MEMBER_CASE) == before


async def test_the_member_check_fails_with_the_refusal_planted_out(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def allowed(self: Any, datasets: Any) -> None:
        return None

    monkeypatch.setattr(DatasetStampingGraph, "_refuse_into_a_composite", allowed)
    async with factory.context() as adapter:
        a, _b = await _loaded(adapter)
        await _rewrite(adapter, a)
        after = await adapter.get_node(a, MEMBER_CASE)
        assert after is not None and after.properties["family_name"] == "MERCER-JONES"


async def test_a_composite_cases_link_between_member_nodes_is_refused(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        a, b = await _loaded(adapter)
        graph = _in_the_composite_case(adapter)
        try:
            tx = await graph.begin_transaction()
            with pytest.raises(CompositeReadOnlyError):
                await graph.upsert_edges(
                    [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")], tx
                )
            await graph.rollback_transaction(tx)
        finally:
            set_case_datasets(None)
        assert await adapter.edges_among([a, b], COMPOSITE_CASE) == []


async def test_a_composite_cases_own_layer_is_still_written(factory: GraphAdapterFactory) -> None:
    """What the ruling keeps: an analyst's own write, naming the case's layer, goes ahead, and a
    case reading only the member does not see it."""
    async with factory.context() as adapter:
        a, b = await _loaded(adapter)
        graph = _in_the_composite_case(adapter)
        try:
            tx = await graph.begin_transaction()
            await graph.upsert_edges(
                [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL", datasets=[LAYER])], tx
            )
            await graph.commit_transaction(tx)
        finally:
            set_case_datasets(None)
        assert len(await adapter.edges_among([a, b], COMPOSITE_CASE)) == 1
        assert await adapter.edges_among([a, b], MEMBER_CASE) == []
