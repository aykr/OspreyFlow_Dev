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


# ---- after a commit: a cited link gone between the judgement and the raise -----------------------

from datetime import UTC, datetime  # noqa: E402

from services.api.rule_evaluation import RuleGate  # noqa: E402

from schemas.domain import DocumentVerificationParams, TypologyRule  # noqa: E402

NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)
SWEEPER = Principal(id="kyc-sweeper", clearance="SECRET", org_unit="unit-1")


class TxGraph(Graph):
    """`Graph`, with the transaction and the writes `write_alert_node` makes, each recorded."""

    def __init__(self, nodes: dict[str, Handling], edges: dict[str, Handling]) -> None:
        super().__init__(nodes, edges)
        self.log: list[str] = []

    async def get_nodes(self, node_ids: Any, principal: Principal) -> list[Any]:
        found = [await self.get_node(i, principal) for i in sorted(set(node_ids))]
        return [n for n in found if n is not None]

    async def begin_transaction(self) -> str:
        self.log.append("begin")
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        self.log.append("commit")

    async def rollback_transaction(self, tx: str) -> None:
        self.log.append("rollback")

    async def upsert_nodes(self, nodes: Any, tx: str) -> list[str]:
        self.log.extend(f"node {n.type}" for n in nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Any, tx: str) -> list[str]:
        self.log.extend(f"edge {e.type}" for e in edges)
        return [e.id for e in edges]


class Stores:
    """The queue, the audit and the signature set: what is saved and said is kept."""

    def __init__(self) -> None:
        self.saved: list[Any] = []
        self.said: list[str] = []
        self.withheld_because: list[str] = []

    async def save(self, alert: Any, *, handlings: Any = None) -> None:
        self.saved.append(alert)

    async def record(self, **kwargs: Any) -> None:
        self.said.append(str(kwargs.get("action")))
        if kwargs.get("action") == "alert_node_withheld":
            self.withheld_because.append(str(kwargs["resolved_query"]["reason"]))

    async def sismember(self, *_: Any) -> bool:
        return False

    async def sadd(self, *_: Any) -> int:
        return 1


def _sweep_gate(graph: TxGraph, stores: Stores) -> RuleGate:
    rule = TypologyRule(id="rule-kyc", investigation_id="case-1", owner_id="deployer", name="Documents",
                        params=DocumentVerificationParams(), trigger="post_commit", created_at=NOW)  # fmt: skip

    async def owner(_: str) -> Principal:
        return SWEEPER

    return RuleGate(rules=[rule], investigation_id="case-1", graph=graph, analytics=None, scheme=SCHEME,  # type: ignore[arg-type]
                    alert_store=stores, audit=stores, valkey=stores, principal_for_owner=owner,  # type: ignore[arg-type]
                    loader=SWEEPER)  # fmt: skip


def _sweep_finding(gate: RuleGate, edge_ids: list[str], node_ids: list[str]) -> Finding:
    return Finding(rule=gate.rules[0], deployer=SWEEPER, typology="document_verification",
                   subject=node_ids[0], refs=(), words="No valid verifying document",
                   node_ids=node_ids, edge_ids=edge_ids)  # fmt: skip


async def test_after_a_commit_an_unreadable_cited_link_raises_the_row_with_no_node() -> None:
    """As the load path already does for an unseen referent (rule_evaluation.py's `pre_commit`:
    no node rather than a guessed one, the row still raised): a link reverted between the judgement
    and the raise leaves the alert without its node, and the sweep goes on. The row is safe: the
    queue's full check withholds it from anyone who may not see its evidence (G2). Red with
    ed8b0aa's behaviour, which raised, and stopped the whole day's KYC sweep (`kyc_sweep.sweep`)."""
    graph, stores = TxGraph({"cust-1": _handling()}, {}), Stores()
    gate = _sweep_gate(graph, stores)
    alert = await gate.raise_committed(_sweep_finding(gate, ["e-reverted"], ["cust-1"]))
    assert alert.alert_node_id is None
    assert [a.id for a in stores.saved] == [alert.id]
    assert "node Alert" not in graph.log and "commit" not in graph.log
    assert "rule_fired" in stores.said


async def test_after_a_commit_an_unreadable_referent_node_still_raises_as_today() -> None:
    """Nodes behave as they did before L2.8: an unreadable referent node stops the raise."""
    graph, stores = TxGraph({}, {}), Stores()
    gate = _sweep_gate(graph, stores)
    with pytest.raises(RuntimeError):
        await gate.raise_committed(_sweep_finding(gate, [], ["cust-gone"]))
    assert stores.saved == []


# ---- why a node was withheld, said in the audit as it is -----------------------------------------
#
# `_raise_row` said "its referents' restricted markings belong to different units" for every alert
# raised without its node, true only of the first of these three. Red with that fixed string: the
# unseen referent and the unreadable link were each said to be a units conflict.


async def test_a_units_conflict_is_said_as_one() -> None:
    restricted = {u: Handling(classification="OFFICIAL", handling_code="R", originator=u, owning_unit=u)
                  for u in ("unit-1", "unit-2")}  # fmt: skip
    graph, stores = TxGraph({"cust-1": restricted["unit-1"], "cust-2": restricted["unit-2"]}, {}), Stores()
    gate = _sweep_gate(graph, stores)
    alert = await gate.raise_committed(_sweep_finding(gate, [], ["cust-1", "cust-2"]))
    assert alert.alert_node_id is None
    assert stores.withheld_because == ["its referents' restricted markings belong to different units"]


async def test_an_unreadable_cited_link_is_said_as_one() -> None:
    graph, stores = TxGraph({"cust-1": _handling()}, {}), Stores()
    gate = _sweep_gate(graph, stores)
    await gate.raise_committed(_sweep_finding(gate, ["e-reverted"], ["cust-1"]))
    (said,) = stores.withheld_because
    assert said.startswith("a link it cites could not be read") and "different units" not in said


async def test_a_referent_unseen_in_the_load_is_said_as_one() -> None:
    """The load path: a referent whose marking cannot be read in the load's transaction, and no
    highest marking given to stand in (`unseen`), is withheld as unseen, and said so when raised."""
    from services.api.rule_evaluation import PreCommitVerdict, RuleWrites

    graph, stores = TxGraph({}, {}), Stores()
    gate = _sweep_gate(graph, stores)
    finding = _sweep_finding(gate, [], ["cust-not-yet-readable"])
    node_id, why, _ = await gate._alert_node_in_load(
        finding, "tx", unseen=None, load_id="load-1", known={}, writes=RuleWrites()
    )
    assert (node_id, why) == (None, "unseen_referent")
    await gate.after_commit(PreCommitVerdict(findings=[(finding, None)], withheld={0: why}))
    (said,) = stores.withheld_because
    assert said.startswith("the marking of something it names could not be read") and "different units" not in said


# ---- a pending write the store merges is cited by its stored id (L2.8b) --------------------------


async def test_a_pending_link_the_store_merges_is_cited_by_the_stored_id() -> None:
    """A second screening hit on a match already held: its pending `SAME_AS` write merges into the
    stored link (one pair, one audience), whose id the store returns. The alert row cites that id,
    never the write's own, which no link holds and which the queue's link check (ADR-146 decision
    10) would read as hidden from every reader. Red before: the row cited the write's id."""
    from schemas.domain import EdgeWrite, Provenance, ProvenanceState, SourceRef

    class MergingGraph(TxGraph):
        async def upsert_edges(self, edges: Any, tx: str) -> list[str]:
            self.log.extend(f"edge {e.type}" for e in edges)
            return ["e-held" if e.type == "SAME_AS" else e.id for e in edges]

    graph = MergingGraph({"cust-1": _handling(), "listed-1": _handling()}, {"e-held": _handling()})
    stores = Stores()
    gate = _sweep_gate(graph, stores)
    match = EdgeWrite(id="e-written", type="SAME_AS", source="cust-1", target="listed-1",
                      properties={"score": 0.98, "model_version": "screening:list"}, basis="probabilistic",
                      provenance=Provenance(state=ProvenanceState.INFERRED, first_seen=NOW,
                                            sources=[SourceRef(document_id="list", locator="e-1", excerpt_hash="")]),
                      handling=_handling(), created_by="kyc-sweeper", created_at=NOW)  # fmt: skip
    finding = Finding(rule=gate.rules[0], deployer=SWEEPER, typology="kyc_screening", subject="cust-1",
                      refs=("hit",), words="cust-1 matches a listed party", node_ids=["cust-1", "listed-1"],
                      edge_ids=["e-written"], pending=(match,))  # fmt: skip
    alert = await gate.raise_committed(finding)
    assert alert.edge_ids == ["e-held"]


# ---- the re-mark never guesses a marking (L2.8b's B9) ---------------------------------------------


async def test_a_re_mark_over_a_link_it_cannot_read_lists_the_alert_unsafe_and_changes_nothing() -> None:
    """`alerts.remark_alerts` computes a node's marking from what its alert rests on, read as the
    service principal. A cited link it cannot read (gone, or pending in the repoint journal) gives
    no safe marking: the alert is listed unsafe and its node left as it is, as `write_alert_node`
    withholds. Red before: the marking was computed from what was left, the link not counted."""
    from services.api.alerts import remark_alerts

    from schemas.domain import Alert, AlertMode

    class Store:
        async def handlings_of(self, alert_id: str) -> None:
            return None

        async def set_alert_node(self, *_: Any, **__: Any) -> bool:
            raise AssertionError("nothing is re-marked")

    graph = TxGraph({"alert-node": _handling(), "cust-1": _handling()}, {})
    alert = Alert(id="a-1", rule_id="typology:r", owner_id="o", mode=AlertMode.FULL, referent_node_ids=["cust-1"],
                  edge_ids=["e-unreadable"], alert_node_id="alert-node", created_at=NOW)  # fmt: skip
    report = await remark_alerts(graph, Store(), SCHEME, [alert])  # type: ignore[arg-type]
    assert report.unsafe == ["a-1"] and report.remarked == []
