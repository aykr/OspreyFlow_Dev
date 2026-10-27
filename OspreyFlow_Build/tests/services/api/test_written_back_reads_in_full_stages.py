"""ADR-130 Amendment 2, "a read that is written back", for the two writers whose full-scope read is
buried in a larger function: the pipeline's online-geocode enrichment (`_run_enrich_stage`, which
supersedes a Location mention with its own provenance) and an alert's true-positive triage
(`alert_queue.dispose`, which confirms a cited `SAME_AS` link). Each is shown red by removing its
`with sources_in_full()`. Hermetic: the graph withholds sources and refuses to write withheld
provenance, as the adapter does."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import services.api.pipeline_run as pipeline_run
from services.api.alert_queue import dispose

from ontology.handling import withhold_sources
from schemas.domain import (
    Alert,
    AlertMode,
    Edge,
    EdgeWrite,
    Node,
    NodeWrite,
    Principal,
    ProvenanceState,
    Subgraph,
)

from .working_set.fakes import FakeGraphPort
from .working_set.test_visible_link import SCHEME, edge, node

TWO = ["Z1001ZZ", "Z1002ZZ"]
SCOPED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[TWO[0]])


class _Graph(FakeGraphPort):
    def __init__(self, nodes: list[Node], edges: list[Edge]) -> None:
        super().__init__(Subgraph(nodes=nodes, edges=edges), graph_nodes=nodes, graph_edges=edges)
        self.node_writes: list[NodeWrite] = []
        self.edge_writes: list[EdgeWrite] = []

    async def suggest_locations(self, name: str, principal: Principal, **_: Any) -> list[Node]:
        return []

    async def supersede_node(self, node_id: str, replacement: NodeWrite, tx: Any) -> str:
        assert not replacement.provenance.sources_withheld, "the write guard refuses this"
        self.node_writes.append(replacement)
        return replacement.id

    async def supersede_edge(self, edge_id: str, replacement: EdgeWrite, tx: Any) -> str:
        assert not replacement.provenance.sources_withheld, "the write guard refuses this"
        self.edge_writes.append(replacement)
        return replacement.id


class _Analytics:
    async def get_geometries(self, refs: Any, principal: Any, version: Any = None) -> list[Any]:
        return []

    async def load_geometries(self, records: Any) -> None:
        return None


async def test_the_online_geocode_supersedes_a_mention_with_its_stored_sources(
    monkeypatch: Any,
) -> None:
    mention = node("loc-1").model_copy(
        update={
            "type": "Location",
            "datasets": list(TWO),
            "properties": {"name": "Quillfeather Wharf"},
        }
    )
    graph = _Graph([mention], [])
    monkeypatch.setattr(pipeline_run, "_upstream_sources", lambda _g, _n: ["src"])
    branches: Any = [
        SimpleNamespace(source_id="src", report=SimpleNamespace(created_node_ids=["loc-1"]))
    ]

    async def online(_name: str) -> tuple[float, float]:
        return (51.5, -0.1)

    report, _ = await pipeline_run._run_enrich_stage(  # noqa: SLF001
        SimpleNamespace(id="enrich", config={"geocoder": "online_allowlist"}),  # type: ignore[arg-type]
        pipeline=None,  # type: ignore[arg-type]
        branches=branches,
        graph=graph,
        principal=SCOPED,
        scheme=SCHEME,
        analytics=_Analytics(),  # type: ignore[arg-type]
        online_geocode=online,
    )

    assert report.matched_online == 1
    assert [s.document_id for s in graph.node_writes[0].provenance.sources] == ["doc-1"]


async def test_a_true_positive_on_a_two_dataset_link_confirms_it_with_its_stored_sources() -> None:
    person = node("p1").model_copy(update={"datasets": list(TWO)})
    other = node("p2").model_copy(update={"datasets": list(TWO)})
    link = edge("sa1", "p1", "p2").model_copy(
        update={
            "type": "SAME_AS",
            "datasets": list(TWO),
            "provenance": edge("x", "p1", "p2").provenance.model_copy(
                update={"state": ProvenanceState.INFERRED}
            ),
        }
    )
    graph = _Graph([person, other], [link])
    alert = Alert(
        id="al-1",
        rule_id="r",
        owner_id="analyst-1",
        mode=AlertMode.FULL,
        referent_node_ids=["p2"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        typology="kyc_screening",
        alert_node_id="p1",
        edge_ids=["sa1"],
    )

    class _Store:
        async def get_case_alert(self, *_a: Any, **_k: Any) -> Alert:
            return alert

        async def set_triage(self, *_a: Any, **_k: Any) -> Alert:
            return alert

    await dispose(
        _Store(),  # type: ignore[arg-type]
        graph,
        "inv-1",
        "al-1",
        SCOPED,
        disposition="true_positive",
        reason="confirmed",
    )

    assert [s.document_id for s in graph.edge_writes[0].provenance.sources] == ["doc-1"]
    assert withhold_sources(link, SCOPED).provenance.sources_withheld  # the premise holds
