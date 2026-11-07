"""`GraphPort` conformance for a composite case's writes (ADR-099 Amendments 14 and 15): what a case
reading a composite writes is written under the composite's own id, and "no case reading only a
member sees what the composite case added". The lane-reviewer's finding 5 on L3.1 measured that a
write naming a node already in a member was merged into it: its properties became the latest
write's, so a member-only case saw the change. The owner ruled (7 November 2026, Amendment 15):
such a write becomes a new node in the composite, linked by `SAME_AS` to the member's node, and no
member changes (rule 6).

Driven through the Conduit's own write path, the stamping graph, with the request's case in scope
as `scope_to_case` holds it, over the real adapter. Shown red (rule 15) with the stamping graph's
check planted out (`_kept_from_members` passing every write through, as before the ruling).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.dataset_scope import DatasetStampingGraph, set_case_datasets, stamping
from services.api.datasets import Dataset, InMemoryDatasetStore

from ontology.handling import load_uk_le_scheme
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


def _in_the_composite_case(adapter: GraphPort, reader: Principal = COMPOSITE_CASE) -> GraphPort:
    """The stamping graph over `adapter`, with a request scoped to the composite case."""
    store = InMemoryDatasetStore()
    for dataset_id in (MEMBER, OTHER_MEMBER):
        store.add(_dataset(dataset_id))
    store.add(_dataset(COMPOSITE, kind="composite", members=[MEMBER, OTHER_MEMBER]))
    store.cases["case-c"] = [COMPOSITE]
    set_case_datasets(reader.datasets, scope=("case-c", store, reader))
    return stamping(adapter, scheme=load_uk_le_scheme())


def _dataset(dataset_id: str, **kind: object) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=dataset_id,
        owning_unit="unit-1",
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        created_by="seed",
        **kind,  # type: ignore[arg-type]
    )


async def _rewrite_through_the_composite_case(adapter: GraphPort) -> tuple[str, str]:
    """A member's node `a`, then the composite case's write naming `a` with one property changed
    (no dataset named, as a writer under a case leaves it). Returns (`a`, the id written)."""
    a, _b = await _loaded(adapter)
    graph = _in_the_composite_case(adapter)
    rewrite = _node("Person", classification="OFFICIAL", family_name="MERCER-JONES").model_copy(
        update={"id": a, "datasets": []}
    )
    tx = await graph.begin_transaction()
    (written,) = await graph.upsert_nodes([rewrite], tx)
    await graph.commit_transaction(tx)
    set_case_datasets(None)
    return a, written


async def test_a_composite_cases_write_to_a_member_node_becomes_a_new_node_linked_by_same_as(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        a, written = await _rewrite_through_the_composite_case(adapter)

        # No member changes: a member-only case reads `a` exactly as loaded.
        member_view = await adapter.get_node(a, MEMBER_CASE)
        assert member_view is not None
        assert member_view.properties["family_name"] == "MERCER"
        assert member_view.datasets == [MEMBER]
        # The composite case's write is a new node of the composite, linked to `a`.
        assert written != a
        fresh = await adapter.get_node(written, COMPOSITE_CASE)
        assert fresh is not None and fresh.datasets == [COMPOSITE]
        assert fresh.properties["family_name"] == "MERCER-JONES"
        links = await adapter.edges_among([written, a], COMPOSITE_CASE)
        assert [(e.type, e.source, e.target) for e in links] == [("SAME_AS", written, a)]
        # Neither the new node nor its link reaches the member-only case.
        assert await adapter.get_node(written, MEMBER_CASE) is None
        assert await adapter.edges_among([written, a], MEMBER_CASE) == []


async def test_the_member_check_fails_with_the_composite_check_planted_out(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def passed_through(self: Any, writes: list[Any]) -> tuple[list[Any], list[Any]]:
        return writes, []

    monkeypatch.setattr(DatasetStampingGraph, "_kept_from_members", passed_through)
    async with factory.context() as adapter:
        a, written = await _rewrite_through_the_composite_case(adapter)
        member_view = await adapter.get_node(a, MEMBER_CASE)
        assert written == a
        assert member_view is not None
        assert member_view.properties["family_name"] == "MERCER-JONES"


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


async def test_the_same_as_takes_the_stricter_marking_of_its_two_ends(
    factory: GraphAdapterFactory,
) -> None:
    """As `same_as_writer._handling_for` marks a `SAME_AS`: a SECRET member node, written again in
    the composite case at OFFICIAL by a reader cleared to SECRET, is linked to its copy at
    SECRET."""
    cleared = COMPOSITE_CASE.model_copy(update={"clearance": "SECRET"})
    async with factory.context() as adapter:
        (secret,), _ = await _write(
            adapter,
            [_node("Person", classification="SECRET", datasets=[MEMBER], family_name="MERCER")],
            [],
        )
        graph = _in_the_composite_case(adapter, cleared)
        rewrite = _node("Person", classification="OFFICIAL", family_name="MERCER").model_copy(
            update={"id": secret, "datasets": []}
        )
        tx = await graph.begin_transaction()
        (copy,) = await graph.upsert_nodes([rewrite], tx)
        await graph.commit_transaction(tx)
        set_case_datasets(None)
        (link,) = [
            e for e in await adapter.edges_among([copy, secret], cleared) if e.type == "SAME_AS"
        ]
        assert link.handling.classification == "SECRET"
