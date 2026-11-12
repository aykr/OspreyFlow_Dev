"""What a screening alert citing two lists writes, and what is stored of it (`06_DECISIONS.md` ADR-146
Amendment 7, points 2, 3 and 5; the lane review of lane/rules-lists, items 1, 5, 8 and 9).

The finding is the real `kyc_rules.screening_finding`'s, over two hits on two lists, "Synthetic list A"
(OFFICIAL) and "Synthetic list B" (SECRET), raised through the real `RuleGate.raise_committed` against
`test_alert_node_marking.py`'s graph, which answers each element by its own stored handling, as the
adapter answers the service reader. Each case was shown red by a plant at its real call site
(`process/lanes/rules/lists/AM7_RED_RECORD.txt`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

from services.api.alerts import remark_alerts
from services.api.kyc_rules import KycContext, screening_finding
from services.api.rule_evaluation import Finding, RuleGate
from services.api.screening import ScreeningEntry, ScreeningHit

from schemas.domain import Alert, AlertMode, Handling, NodeWrite
from tests.services.api.test_alert_node_marking import (
    NOW,
    SCHEME,
    SWEEPER,
    Stores,
    TxGraph,
    _handling,
    _sweep_gate,
)

ENTRY_A = ScreeningEntry(id="Synthetic list A:a-1", list_name="Synthetic list A", listing="sanction",
                         entity_type="Person", name="PETROVA, Elena")  # fmt: skip
ENTRY_B = ScreeningEntry(id="Synthetic list B:b-1", list_name="Synthetic list B", listing="sanction",
                         entity_type="Person", name="Elena PETROVA", classification="SECRET",
                         handling_code="P")  # fmt: skip
CUSTOMER = SimpleNamespace(id="cust-1", type="Organisation", handling=_handling(),
                           properties={"name": "Halcyon Marine Ltd"})  # fmt: skip
OWNER = SimpleNamespace(id="owner-1", type="Person", handling=_handling(),
                        properties={"family_name": "Petrov", "given_names": "Elena"})  # fmt: skip


class WritingGraph(TxGraph):
    """`TxGraph`, keeping every write `write_alert_node` makes, and finding no listed party yet held
    (`find_node`, with `also` as the port takes it). A write it is told to merge (`merge`) is
    answered with the held element's id, as the store merges a pair it already holds; a new write
    is read back only once its transaction commits, as the adapter answers a reader outside it."""

    def __init__(self, nodes: dict[str, Handling], edges: dict[str, Handling],
                 merge: dict[str, str] | None = None) -> None:  # fmt: skip
        super().__init__(nodes, edges)
        self.merge = merge or {}
        self.writes: list[Any] = []
        self.staged: list[Any] = []

    async def find_node(self, *_: Any, also: Any = None) -> None:
        return None

    async def upsert_nodes(self, nodes: Any, tx: str) -> list[str]:
        self.writes.extend(nodes)
        ids = [self.merge.get(n.properties.get("list_name", ""), n.id) if n.type == "Person" else n.id
               for n in nodes]  # fmt: skip
        self.staged.extend(("node", i, n.handling) for n, i in zip(nodes, ids, strict=True) if i == n.id)
        return ids

    async def upsert_edges(self, edges: Any, tx: str) -> list[str]:
        self.writes.extend(edges)
        ids = [self.merge.get(f"{e.type}:{e.target}", e.id) for e in edges]
        self.staged.extend(("edge", i, e.handling) for e, i in zip(edges, ids, strict=True) if i == e.id)
        return ids

    async def commit_transaction(self, tx: str) -> None:
        await super().commit_transaction(tx)
        for kind, element_id, handling in self.staged:
            (self.nodes if kind == "node" else self.edges)[element_id] = handling
        self.staged.clear()


async def _finding(graph: WritingGraph, gate: RuleGate) -> Finding:
    ctx = KycContext(graph=graph, scheme=SCHEME, screening=None, compute=None, today=date(2026, 11, 12))  # type: ignore[arg-type]
    hits = [ScreeningHit(entry=ENTRY_A, score=0.97), ScreeningHit(entry=ENTRY_B, score=0.95)]
    return await screening_finding(gate.rules[0], SWEEPER, CUSTOMER, OWNER, hits, ctx,  # type: ignore[arg-type]
                                   chain_words=" is ultimately owned 48% by Elena Petrov")  # fmt: skip


def _world(merge: dict[str, str] | None = None, held: dict[str, Handling] | None = None) -> tuple[WritingGraph, Stores, RuleGate]:
    graph = WritingGraph({"cust-1": _handling(), "owner-1": _handling(), **(held or {})}, dict(held or {}),
                         merge)  # fmt: skip
    stores = Stores()
    return graph, stores, _sweep_gate(graph, stores)


def _alert_node(graph: WritingGraph) -> NodeWrite:
    (node,) = [w for w in graph.writes if getattr(w, "type", None) == "Alert"]
    return node


def _alerted_on(graph: WritingGraph) -> dict[str, str]:
    """Each `ALERTED_ON`'s target and its classification."""
    return {w.target: w.handling.classification for w in graph.writes if w.type == "ALERTED_ON"}


async def test_one_finding_cites_each_list_and_its_words_name_none() -> None:
    graph, _, gate = _world()
    finding = await _finding(graph, gate)
    assert [c.words.split("(")[1].split(")")[0] for c in finding.citations] == ["Synthetic list A", "Synthetic list B"]
    assert "Synthetic list" not in finding.words and "matches an entry on a screening list" in finding.words


async def test_the_alert_node_names_no_list_and_is_marked_by_what_is_outside_its_citations() -> None:
    """Item 1: the node's sources named every list's entry, the SECRET one's too, on a node an
    OFFICIAL reader reads. Item 9: its words and the audit entry's, from the code, not a fixture."""
    graph, stores, gate = _world()
    alert = await gate.raise_committed(await _finding(graph, gate))
    node = _alert_node(graph)
    assert node.handling.classification == "OFFICIAL"
    text = node.model_dump_json()
    assert "Synthetic list" not in text, text
    assert [s.locator for s in node.provenance.sources] == ["owner-1"]
    assert alert.words is not None and "Synthetic list" not in alert.words
    assert "rule_fired" in stores.said


async def test_each_cited_partys_alerted_on_is_marked_by_its_list() -> None:
    graph, _, gate = _world()
    await gate.raise_committed(await _finding(graph, gate))
    marks = _alerted_on(graph)
    listed = {w.properties["list_name"]: w.id for w in graph.writes
              if getattr(w, "type", None) == "Person" and "list_name" in w.properties}  # fmt: skip
    assert marks[listed["Synthetic list B"]] == "SECRET" and marks[listed["Synthetic list A"]] == "OFFICIAL"
    assert marks["cust-1"] == "OFFICIAL"


async def test_a_match_merged_on_one_list_keeps_the_new_lists_marking() -> None:
    """Item 5: list A's party and match already held (merged), list B's new. Red before: every
    pending write was dropped once one merged, B's new party and match could not be read back, and
    the node was withheld (`UnreadableAlertLink`) or B's link marked below B's list."""
    held = {"l-a-held": _handling(), "s-a-held": _handling()}
    graph, stores, gate = _world(merge={"Synthetic list A": "l-a-held", "SAME_AS:l-a-held": "s-a-held"},
                                 held=held)  # fmt: skip
    alert = await gate.raise_committed(await _finding(graph, gate))
    assert alert.alert_node_id is not None and stores.withheld_because == []
    assert "l-a-held" in alert.referent_node_ids
    assert any(c.node_ids == ["l-a-held"] for c in alert.citations)
    marks = _alerted_on(graph)
    (b_party,) = [w.id for w in graph.writes if getattr(w, "type", None) == "Person"
                  and w.properties.get("list_name") == "Synthetic list B"]  # fmt: skip
    assert marks[b_party] == "SECRET" and marks["l-a-held"] == "OFFICIAL"


async def test_a_cited_party_no_single_marking_joins_to_the_node_gets_no_alerted_on() -> None:
    """A list whose match is restricted to another unit (as stored) cannot be joined to the node's
    marking: that one link is not written; the node and the rest are."""
    other = Handling(classification="OFFICIAL", handling_code="R", originator="unit-2", owning_unit="unit-2")
    graph, _, gate = _world(merge={"Synthetic list A": "l-a-held", "SAME_AS:l-a-held": "s-a-held"},
                            held={"l-a-held": other, "s-a-held": other})  # fmt: skip
    await gate.raise_committed(await _finding(graph, gate))
    marks = _alerted_on(graph)
    assert "l-a-held" not in marks and _alert_node(graph) is not None and marks["cust-1"] == "OFFICIAL"


async def test_what_the_trends_count_it_by_holds_every_lists_marking() -> None:
    """Point 5: the trends count the alert only for a reader cleared for all it rests on, its
    citations included, so they never count it for a reader not shown it."""
    graph, stores, gate = _world()
    saved: list[Any] = []

    async def save(alert: Any, *, handlings: Any = None) -> None:
        saved.append(handlings)

    stores.save = save  # type: ignore[method-assign]
    await gate.raise_committed(await _finding(graph, gate))
    # Read back as the deployer after the commit: the new writes are the graph's now.
    (handlings,) = saved
    assert handlings is not None and "SECRET" in {h.classification for h in handlings}


async def test_a_re_mark_reads_only_what_is_outside_the_citations() -> None:
    """Point 5: a node marked OFFICIAL over a SECRET citation is right as it is; red with the
    re-mark reading the citations too: raised to SECRET, hidden from the reader cleared for A."""

    class Store:
        async def handlings_of(self, alert_id: str) -> list[Handling]:
            return [_handling("SECRET")]

        async def set_alert_node(self, *_: Any, **__: Any) -> bool:
            raise AssertionError("nothing is re-marked")

    graph = TxGraph({"alert-node": _handling(), "cust-1": _handling(), "l-a": _handling(),
                     "l-b": _handling("SECRET")},
                    {"s-a": _handling(), "s-b": _handling("SECRET")})  # fmt: skip
    from schemas.domain import AlertCitation

    alert = Alert(id="a-1", rule_id="typology:r", owner_id="o", mode=AlertMode.FULL,
                  referent_node_ids=["cust-1", "l-a", "l-b"], edge_ids=["s-a", "s-b"],
                  alert_node_id="alert-node", created_at=NOW,
                  citations=[AlertCitation(words="A", node_ids=["l-a"], edge_ids=["s-a"]),
                             AlertCitation(words="B", node_ids=["l-b"], edge_ids=["s-b"])])  # fmt: skip
    report = await remark_alerts(graph, Store(), SCHEME, [alert])  # type: ignore[arg-type]
    assert report.remarked == [] and report.unsafe == []


def test_no_route_answers_the_ids_a_loads_rules_wrote() -> None:
    """The lane review's item 3: a load's rules write a SECRET list's party and match into the
    load (`LoadReport.rule_node_ids` and the rule link lists), which its loader, not its deployer,
    may not read. A route answers `LoadReportView` (`load_records._load_view`), which holds no id
    list at all: none of the rule writes' ids, nor how many."""
    from schemas.ingest import BranchRunReportView, LoadReportView, PipelineRunReportView

    for view in (LoadReportView, BranchRunReportView, PipelineRunReportView):
        assert not [f for f in view.model_fields if f.endswith("_ids")], view
    assert not {"rule_node_ids", "rule_created_edge_ids", "rule_merged_edge_ids"} & set(LoadReportView.model_fields)


async def test_a_match_reuses_its_own_lists_party_never_another_lists_of_the_same_name() -> None:
    """The lane review's item 6: both lists name PETROVA, and list B's party is the first a lookup
    by name finds. A hit on list A reuses list A's party (asked for by its list, `also`, as the port
    takes it). Red with the lookup by name alone and the list checked after: B's came back, did not
    fit, and A's party was written again, a duplicate whose match no other alert shares."""

    class HeldParties(WritingGraph):
        held = [
            SimpleNamespace(id="b-party", type="Person", handling=_handling(),
                            properties={"family_name": "Petrova", "list_name": "Synthetic list B"}),
            SimpleNamespace(id="a-party", type="Person", handling=_handling(),
                            properties={"family_name": "Petrova", "list_name": "Synthetic list A"}),
        ]  # fmt: skip

        async def find_node(self, entity_type: str, field: str, value: str, principal: Any,
                            *, also: Any = None) -> Any:  # fmt: skip
            for node in self.held:
                if (node.type == entity_type and node.properties.get(field) == value
                        and all(node.properties.get(k) == v for k, v in (also or {}).items())):  # fmt: skip
                    return node
            return None

    graph = HeldParties({"cust-1": _handling(), "owner-1": _handling()}, {})
    gate = _sweep_gate(graph, Stores())
    ctx = KycContext(graph=graph, scheme=SCHEME, screening=None, compute=None, today=date(2026, 11, 12))  # type: ignore[arg-type]
    finding = await screening_finding(gate.rules[0], SWEEPER, CUSTOMER, OWNER,  # type: ignore[arg-type]
                                      [ScreeningHit(entry=ENTRY_A, score=0.97)], ctx)  # fmt: skip
    (citation,) = finding.citations
    assert citation.node_ids == ["a-party"]
    assert not [w for w in finding.pending if getattr(w, "type", None) == "Person"]
