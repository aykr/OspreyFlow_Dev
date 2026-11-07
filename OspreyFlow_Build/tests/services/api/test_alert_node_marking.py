"""The `Alert` node is never marked lower than anything it cites, its links included
(`06_DECISIONS.md` ADR-109 ruling 2; ADR-146 decision 10; rule 3). The node carries the finding's
words, and is read wherever nodes are (the canvas, search) at its own marking.

Found in L2.8 (the orchestrator's item ii): the marking counted the cited transactions, what the
finding writes alongside and the referenced nodes, but not the cited links already in the graph, so a
link marked above its ends and its transactions left the node, and its words, readable by someone
who may not see the link. Red before the fix: the marking was the nodes' and transactions', OFFICIAL.
The live counterpart (the node not readable as a node, on the canvas or in search) is
`test_alert_evidence_withheld_live.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api.rule_evaluation import Finding, _referent_handlings, alert_handling

from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal

SCHEME = load_uk_le_scheme()


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(classification=classification, handling_code="P", originator="unit-1",
                    owning_unit="unit-1")  # fmt: skip


class Graph:
    """Answers as the adapter does, to the service reader the marking is read as: each element by
    its own stored handling; an id it does not hold is absent."""

    def __init__(self, nodes: dict[str, Handling], edges: dict[str, Handling]) -> None:
        self.nodes, self.edges = nodes, edges

    async def get_node(self, node_id: str, principal: Principal, **_: object) -> Any:
        h = self.nodes.get(node_id)
        return None if h is None else type("N", (), {"id": node_id, "handling": h})()

    async def get_edges(self, edge_ids: Any, principal: Principal) -> list[Any]:
        if isinstance(edge_ids, str):
            raise TypeError("edge_ids must be a sequence of ids")
        return [type("E", (), {"id": i, "handling": self.edges[i]})()
                for i in sorted(set(edge_ids)) if i in self.edges]  # fmt: skip


def _finding(edge_ids: list[str]) -> Finding:
    return Finding(rule=None, deployer=Principal(id="deployer", clearance="SECRET", org_unit="unit-1"),  # type: ignore[arg-type]
                   typology="structuring", subject="n-a", refs=(), words="A. Customer paid B. Customer",
                   node_ids=["n-a", "n-b"], edge_ids=edge_ids)  # fmt: skip


async def test_an_alert_over_a_link_marked_above_its_ends_is_marked_as_the_link() -> None:
    graph = Graph({"n-a": _handling(), "n-b": _handling()}, {"e-secret": _handling("SECRET")})
    handlings = await _referent_handlings(graph, SCHEME, _finding(["e-secret"]), None, {})  # type: ignore[arg-type]
    marking = alert_handling(SCHEME, handlings)
    assert marking is not None and marking.classification == "SECRET"


async def test_a_cited_link_whose_marking_cannot_be_read_is_never_guessed() -> None:
    """As for a node: the load's highest possible marking stands in, else no node at all."""
    graph = Graph({"n-a": _handling(), "n-b": _handling()}, {})
    unseen = _handling("SECRET")
    handlings = await _referent_handlings(graph, SCHEME, _finding(["e-gone"]), unseen, {})  # type: ignore[arg-type]
    assert alert_handling(SCHEME, handlings).classification == "SECRET"  # type: ignore[union-attr]
    with pytest.raises(RuntimeError):
        await _referent_handlings(graph, SCHEME, _finding(["e-gone"]), None, {})  # type: ignore[arg-type]
