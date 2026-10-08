"""Running a starter question (ADR-100 Amendment 7): what matched, and the links among it, for
the canvas, all of it or nothing.

What a mistake would do, and the case that catches it:

- a match resting on a node or link the reader cannot see, or the links among the matched nodes
  including a hidden one (`test_a_run_is_what_the_reader_can_see_and_the_links_among_it`, real
  ArcadeDB: the store's access step is under test, not a fake's);
- more than the limit matching, and the first slice handed over as the answer
  (`test_at_the_limit_nothing_is_matched_and_it_says_at_least_how_many`);
- a pattern sent by the caller rather than one offered for the case
  (`test_only_a_question_offered_for_the_case_runs`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.explore import ExploreService, StarterNotOffered, TooManyMatches

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    Handling,
    NodeWrite,
    PatternQuery,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.explore import TypeCounts

ONTOLOGY = load_default_ontology()
READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["fixture"])
CLEARED = READER.model_copy(update={"clearance": "SECRET"})
CHAIN = "chain:USES:Person:Endpoint:COMMUNICATED_WITH:Endpoint"


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="fixture", locator="row:1", excerpt_hash="")],
        first_seen=datetime.now(UTC),
    )


def _handling(classification: str) -> Handling:
    return Handling(classification=classification, handling_code="P", originator="unit-1",
                    owning_unit="unit-1")


def _node(kind: str, classification: str = "OFFICIAL") -> NodeWrite:
    phone = {"value_normalised": f"+44{new_id()[:9]}"}
    props = {"family_name": "Test"} if kind == "Person" else phone
    return NodeWrite(id=new_id(), type=kind, properties=props, provenance=_provenance(),
                     handling=_handling(classification), created_by="loader",
                     created_at=datetime.now(UTC), datasets=["fixture"])


def _link(kind: str, a: str, b: str, classification: str = "OFFICIAL") -> EdgeWrite:
    return EdgeWrite(id=new_id(), type=kind, source=a, target=b, provenance=_provenance(),
                     handling=_handling(classification), created_by="loader",
                     created_at=datetime.now(UTC), datasets=["fixture"])


async def test_a_run_is_what_the_reader_can_see_and_the_links_among_it() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        kinds = {"a": "Person", "b": "Person", "c": "Person", "x": "Endpoint", "y": "Endpoint",
                 "z": "Endpoint", "s": "Endpoint", "w": "Endpoint", "v": "Endpoint"}
        writes = {n: _node(k, "SECRET" if n == "s" else "OFFICIAL") for n, k in kinds.items()}
        ids = {n: w.id for n, w in writes.items()}
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(list(writes.values()), tx)
        # a → x → y is seen; b → z → s ends at a SECRET node; c → w → v runs over a SECRET link;
        # a's own link to y, between two nodes the run matches, is SECRET.
        await graph.upsert_edges(
            [_link("USES", ids[p], ids[e]) for p, e in [("a", "x"), ("b", "z"), ("c", "w")]]
            + [_link("COMMUNICATED_WITH", ids[p], ids[e]) for p, e in [("x", "y"), ("z", "s")]]
            + [_link("COMMUNICATED_WITH", ids["w"], ids["v"], "SECRET"),
               _link("USES", ids["a"], ids["y"], "SECRET")],
            tx,
        )
        await graph.commit_transaction(tx)
        explore = ExploreService(graph, None)
        nodes, edges = await explore.run_starter(READER, ONTOLOGY, CHAIN)
        name = {v: k for k, v in ids.items()}
        assert {name[n.id] for n in nodes} == {"a", "x", "y"}
        assert sorted((name[e.source], name[e.target]) for e in edges) == [("a", "x"), ("x", "y")]
        # The filter is real: cleared, the other two chains and a's link to y are there too.
        cleared, links = await explore.run_starter(CLEARED, ONTOLOGY, CHAIN)
        assert {name[n.id] for n in cleared} == set(kinds)
        assert ("a", "y") in {(name[e.source], name[e.target]) for e in links}


class _Graph:
    def __init__(self, count: int) -> None:
        self.count = count
        self.matched: list[PatternQuery] = []

    async def type_counts(self, principal: Principal) -> TypeCounts:
        return TypeCounts(
            nodes={"Person": 3, "Endpoint": 3}, edges={"USES": 5, "COMMUNICATED_WITH": 5}
        )

    async def match_count(
        self, pattern: PatternQuery, principal: Principal, *, ceiling: int
    ) -> int:
        return min(self.count, ceiling)

    async def match(self, pattern: PatternQuery, principal: Principal) -> Any:
        self.matched.append(pattern)
        raise AssertionError("matched past the limit")


async def test_at_the_limit_nothing_is_matched_and_it_says_at_least_how_many() -> None:
    graph = _Graph(count=5000)
    explore = ExploreService(graph, None)  # type: ignore[arg-type]
    with pytest.raises(TooManyMatches) as raised:
        await explore.run_starter(READER, ONTOLOGY, CHAIN)
    assert raised.value.at_least == 1000
    assert graph.matched == []


async def test_only_a_question_offered_for_the_case_runs() -> None:
    explore = ExploreService(_Graph(count=1), None)  # type: ignore[arg-type]
    for question_id in ("chain:FAMILY_OF:Person:Person:FAMILY_OF:Person", "anything"):
        with pytest.raises(StarterNotOffered):
            await explore.run_starter(READER, ONTOLOGY, question_id)
