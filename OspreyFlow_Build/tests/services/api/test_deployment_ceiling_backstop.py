"""ADR-148 decision 10's backstop (L1.10): every write through the dataset-stamping graph (every
load, every seed, every analyst write into a dataset) is refused before the store is reached when
it is marked above the deployment's highest marking, so a path the engine's own check never sees
(a demo seed writing the graph directly) still cannot write above the ceiling."""

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
