"""Every dataset a graph element names is one the registry holds (ADR-099 Amendment 6, the owner:
"maintain a unique referential integrity across datasets even if they get named similarly").

The graph cannot hold a foreign key into Postgres, so the Conduit's one write path, the stamping
graph, checks each write's datasets against the registry before the store sees it. What a mistake
would do, and the case that catches it:

- an element naming a dataset nobody registered, which no case could ever be given and so no one
  could read (`test_a_write_naming_an_unregistered_dataset_is_refused_and_nothing_is_written`);
- the same through the case's own datasets, or the bulk path
  (`test_the_cases_dataset_is_checked_too`, `test_the_bulk_path_is_checked_too`);
- a registry asked again for every write of an id it already confirmed
  (`test_a_confirmed_dataset_is_not_asked_again`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.dataset_scope import (
    UnknownDatasetError,
    set_case_datasets,
    stamping,
)

from schemas.domain import EdgeWrite, NodeWrite, Provenance, ProvenanceState, SourceRef

PROVENANCE = Provenance(
    state=ProvenanceState.ASSERTED,
    sources=[SourceRef(document_id="d", locator="p.1", excerpt_hash="a" * 64)],
    first_seen=datetime(2026, 1, 1, tzinfo=UTC),
)
HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "u",
    "owning_unit": "u",
}


def _node(node_id: str, datasets: list[str] | None = None) -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type="Person",
        properties={"family_name": "X"},
        provenance=PROVENANCE,
        handling=HANDLING,  # type: ignore[arg-type]
        created_by="t",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        datasets=datasets or [],
    )


def _edge(datasets: list[str]) -> EdgeWrite:
    return EdgeWrite(
        id="e1",
        type="ASSOCIATE_OF",
        source="a",
        target="b",
        provenance=PROVENANCE,
        handling=HANDLING,  # type: ignore[arg-type]
        created_by="t",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        datasets=datasets,
    )


class _Registry:
    def __init__(self, held: set[str]) -> None:
        self.held = held
        self.asked: list[list[str]] = []

    async def known(self, dataset_ids: Sequence[str]) -> set[str]:
        self.asked.append(sorted(dataset_ids))
        return {d for d in dataset_ids if d in self.held}


class _Store:
    def __init__(self) -> None:
        self.nodes: list[NodeWrite] = []
        self.edges: list[EdgeWrite] = []

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: Any) -> list[str]:
        self.nodes.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: Any) -> list[str]:
        self.edges.extend(edges)
        return [e.id for e in edges]


class _BulkStore(_Store):
    async def bulk_load_edges(self, edges: Sequence[EdgeWrite], **kwargs: Any) -> Any:
        self.edges.extend(edges)
        return None

    async def bulk_load_nodes(self, nodes: Sequence[NodeWrite], **kwargs: Any) -> Any:
        self.nodes.extend(nodes)
        return None


@pytest.fixture(autouse=True)
def _no_case() -> Any:
    set_case_datasets(None)
    yield
    set_case_datasets(None)


async def test_a_write_naming_an_unregistered_dataset_is_refused_and_nothing_is_written() -> None:
    store, registry = _Store(), _Registry({"fixture"})
    graph = stamping(store, registry=registry)  # type: ignore[arg-type]
    with pytest.raises(UnknownDatasetError, match="ghost"):
        await graph.upsert_nodes([_node("a", ["fixture"]), _node("b", ["ghost"])], "tx")
    assert store.nodes == []
    with pytest.raises(UnknownDatasetError):
        await graph.upsert_edges([_edge(["ghost"])], "tx")
    assert store.edges == []
    await graph.upsert_nodes([_node("a", ["fixture"])], "tx")
    assert [n.id for n in store.nodes] == ["a"]


async def test_the_cases_dataset_is_checked_too() -> None:
    store = _Store()
    graph = stamping(store, registry=_Registry({"fixture"}))  # type: ignore[arg-type]
    set_case_datasets(["ghost"])
    with pytest.raises(UnknownDatasetError):
        await graph.upsert_nodes([_node("a")], "tx")
    set_case_datasets(["fixture"])
    await graph.upsert_nodes([_node("a")], "tx")
    assert store.nodes[0].datasets == ["fixture"]


async def test_the_bulk_path_is_checked_too() -> None:
    store = _BulkStore()
    graph: Any = stamping(store, registry=_Registry({"fixture"}))  # type: ignore[arg-type]
    with pytest.raises(UnknownDatasetError):
        await graph.bulk_load_edges([_edge(["ghost"])])
    assert store.edges == []


async def test_a_confirmed_dataset_is_not_asked_again() -> None:
    registry = _Registry({"fixture"})
    graph = stamping(_Store(), registry=registry)  # type: ignore[arg-type]
    await graph.upsert_nodes([_node("a", ["fixture"])], "tx")
    await graph.upsert_nodes([_node("b", ["fixture"])], "tx")
    assert registry.asked == [["fixture"]]


async def test_without_a_registry_nothing_is_checked() -> None:
    """A test double or a script that writes before any registry exists: named here so it is a
    choice, not an accident."""
    store = _Store()
    await stamping(store).upsert_nodes([_node("a", ["anything"])], "tx")  # type: ignore[arg-type]
    assert len(store.nodes) == 1
