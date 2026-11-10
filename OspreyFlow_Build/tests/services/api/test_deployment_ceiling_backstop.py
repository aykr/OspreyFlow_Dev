"""ADR-148 decision 10's backstop (L1.10): every new element written through the dataset-stamping
graph (an upsert, a bulk load or a correction: a load, a seed, an analyst's write) is refused
before the store is reached when it is marked above the deployment's highest marking, so a path
the engine's own check never sees (a demo seed writing the graph directly) still cannot write
above the ceiling."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.dataset_scope import stamping
from services.ingest.ceiling import AboveTheDeploymentCeiling

from schemas.domain import EdgeWrite, Handling, NodeWrite

from .test_dataset_scope import PROVENANCE, _RecordingGraph


def _handling(classification: str) -> Handling:
    return Handling(
        classification=classification, handling_code="P", originator="u", owning_unit="u"
    )


def _node(classification: str) -> NodeWrite:
    return NodeWrite(
        id=f"n-{classification}", type="Person", properties={"family_name": "X"},
        provenance=PROVENANCE, handling=_handling(classification), created_by="seed",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )  # fmt: skip


def _edge(classification: str) -> EdgeWrite:
    return EdgeWrite(
        id=f"e-{classification}", type="ASSOCIATE_OF", source="a", target="b",
        provenance=PROVENANCE, handling=_handling(classification), created_by="seed",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )  # fmt: skip


class _Bulk(_RecordingGraph):
    def __init__(self) -> None:
        super().__init__()
        self.bulk: list[EdgeWrite] = []

    async def bulk_load_edges(self, edges: list[EdgeWrite], **kwargs: Any) -> str:
        self.bulk.extend(edges)
        return "loaded"


@pytest.fixture(autouse=True)
def _ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "OFFICIAL-SENSITIVE")


async def test_a_node_above_the_ceiling_never_reaches_the_store() -> None:
    inner = _RecordingGraph()
    graph = stamping(inner, dataset="fixture-corp")  # type: ignore[arg-type]
    with pytest.raises(AboveTheDeploymentCeiling) as raised:
        await graph.upsert_nodes([_node("OFFICIAL"), _node("SECRET")], tx=None)
    assert inner.nodes == [], "a node was written before the refusal"
    assert "OFFICIAL-SENSITIVE" in str(raised.value)


async def test_a_link_above_the_ceiling_never_reaches_the_store() -> None:
    inner = _RecordingGraph()
    graph = stamping(inner, dataset="fixture-corp")  # type: ignore[arg-type]
    with pytest.raises(AboveTheDeploymentCeiling):
        await graph.upsert_edges([_edge("SECRET")], tx=None)
    assert inner.edges == []


async def test_a_bulk_load_above_the_ceiling_never_reaches_the_store() -> None:
    inner = _Bulk()
    graph = stamping(inner, dataset="enron")  # type: ignore[arg-type]
    with pytest.raises(AboveTheDeploymentCeiling):
        await graph.bulk_load_edges([_edge("SECRET")], chunk_size=10)  # type: ignore[attr-defined]
    assert inner.bulk == []


async def test_writes_at_the_ceiling_are_written() -> None:
    inner = _Bulk()
    graph = stamping(inner, dataset="enron")  # type: ignore[arg-type]
    await graph.upsert_nodes([_node("OFFICIAL-SENSITIVE")], tx=None)
    await graph.upsert_edges([_edge("OFFICIAL")], tx=None)
    await graph.bulk_load_edges([_edge("OFFICIAL-SENSITIVE")])  # type: ignore[attr-defined]
    assert (len(inner.nodes), len(inner.edges), len(inner.bulk)) == (1, 1, 1)


class _Correcting(_RecordingGraph):
    def __init__(self) -> None:
        super().__init__()
        self.corrections: list[Any] = []

    async def supersede_node(self, node_id: str, replacement: NodeWrite, tx: Any, **kw: Any) -> str:
        self.corrections.append(replacement)
        return replacement.id

    async def supersede_edge(self, edge_id: str, replacement: EdgeWrite, tx: Any, **kw: Any) -> str:
        self.corrections.append(replacement)
        return replacement.id


async def test_a_correction_above_the_ceiling_never_reaches_the_store() -> None:
    """A correction (`supersede_node`, `supersede_edge`: the analyst's edits, the extractions'
    writer, a picture) writes a new element as a write does (the lane review of L1.10, item 7)."""
    inner = _Correcting()
    graph = stamping(inner, dataset="case-layer")  # type: ignore[arg-type]
    with pytest.raises(AboveTheDeploymentCeiling):
        await graph.supersede_node("n-old", _node("SECRET"), tx=None)
    with pytest.raises(AboveTheDeploymentCeiling):
        await graph.supersede_edge("e-old", _edge("SECRET"), tx=None, old_type="ASSOCIATE_OF")
    assert inner.corrections == []
    await graph.supersede_node("n-old", _node("OFFICIAL"), tx=None)
    assert len(inner.corrections) == 1
