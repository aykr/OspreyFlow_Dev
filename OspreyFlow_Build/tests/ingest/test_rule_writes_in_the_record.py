"""ADR-127 decision 6: what the case's rules write into a load belongs to the load. A pre-commit
rule's `Alert` node, its `ALERTED_ON` links and anything the finding writes alongside (`pending`)
are written inside the load's own transaction, so a revert of the load that is to take back what it
wrote must find them in its record. What a mistake would do, and the case that catches it:

- an alert left out of the record, so a reverted load leaves an alert pointing at nodes that are
  gone (`test_a_pre_commit_alert_and_its_links_are_in_the_loads_record`);
- what a finding writes alongside its alert left out
  (`test_what_a_finding_writes_alongside_its_alert_is_in_the_record`);
- a pending link that merged into a link another load wrote recorded as created, so a revert takes
  back the other load's link (`test_a_pending_link_that_merges_into_another_loads_link_is_merged`),
  or into the load's own recorded as a merge, so the load is refused its own revert
  (`test_a_pending_link_that_merges_into_the_loads_own_link_is_neither`);
- an alert raised after the commit, which is written in a transaction of its own, left out of the
  record (`test_an_alert_raised_after_the_commit_is_added_to_the_record`).

The rules run for real (`RuleGate.pre_commit`, `post_commit`, `write_alert_node`) over the shared
merging graph stand-in; only the judgement is replaced, by a finding the test hands back, and the
queue, the audit and the signature store by fakes that keep what they are given."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.rule_evaluation import Finding, RuleGate
from services.api.studio_publish import load_with_rules, post_commit_notes

from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    StructuringParams,
    TypologyRule,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    local_staging,
)
from tests.ingest.test_load_record_created_and_merged import (
    LOADER,
    MergingGraph,
    _recipe,
    _row,
)

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 10, 25, 9, tzinfo=UTC)
MARKING = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)


class _Fake:
    """Queue, audit and signature store in one: each accepts what it is given."""

    def __init__(self) -> None:
        self.saved: list[Any] = []

    async def save(self, alert: Any) -> None:
        self.saved.append(alert)

    async def record(self, **kwargs: Any) -> None:
        return None

    async def sismember(self, *args: Any) -> bool:
        return False

    async def sadd(self, *args: Any) -> int:
        return 1


class RuleGraph(MergingGraph):
    """The merging stand-in, able to read back a committed node's marking, as an alert raised after
    the commit does for its referents (`_referent_handlings`)."""

    async def get_node(self, node_id: str, principal: Any, **kwargs: Any) -> Any:
        found = next((n for n in self.committed_nodes if n.id == node_id), None)
        return None if found is None else SimpleNamespace(handling=found.handling)


def _rule(trigger: str) -> TypologyRule:
    return TypologyRule(
        id="rule-1", investigation_id="case-1", owner_id=LOADER.id, name="Cash in",
        params=StructuringParams(threshold=1000, window_days=7, minimum_count=2),
        trigger=trigger, created_at=NOW,
    )  # type: ignore[arg-type]  # fmt: skip


def _gate(rule: TypologyRule, graph: Any, monkeypatch: pytest.MonkeyPatch, make_finding: Any) -> RuleGate:
    fake = _Fake()

    async def owner(_: str) -> Principal:
        return LOADER

    gate = RuleGate(
        rules=[rule], investigation_id="case-1", graph=graph, analytics=None, scheme=SCHEME,
        alert_store=fake, audit=fake, valkey=fake, principal_for_owner=owner, loader=LOADER,
    )  # type: ignore[arg-type]  # fmt: skip

    async def judge(self: RuleGate, rule: Any, deployer: Any, events: Any, written: Any) -> list[Finding]:
        return [make_finding(rule, deployer, written)]

    monkeypatch.setattr(RuleGate, "_judge_rule", judge)
    monkeypatch.setattr(RuleGate, "_rows_for", staticmethod(lambda *a: []))
    return gate


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.INFERRED,
        sources=[SourceRef(document_id="screening", locator="x", excerpt_hash="")],
        first_seen=NOW,
    )


def _finding(rule: Any, deployer: Any, written: Any, **extra: Any) -> Finding:
    nodes = [w.id for w in written if isinstance(w, NodeWrite) and w.type == "Endpoint"][:2]
    return Finding(
        rule=rule, deployer=deployer, typology="structuring", subject=nodes[0], refs=tuple(nodes),
        words="cash in, in small amounts", node_ids=nodes, **extra,
    )  # fmt: skip


def _record(report: Any) -> Any:
    from services.ingest.load_ledger import load_record_from_report

    return load_record_from_report(
        report, source="private_cash.csv", created_by="loader-1", started_at=NOW, now=NOW,
        investigation_id="case-1",
    )  # fmt: skip


async def _load(graph: Any, gate: RuleGate, rows: list[dict[str, str]], load_id: str) -> Any:
    report, _events, _held = await load_with_rules(
        _recipe(), rows, LOADER, graph=graph, ontology=ONTOLOGY, load_id=load_id,
        investigation_scope="case-1", source="private_cash.csv", media=InMemoryMediaStore(),
        rules=gate, scheme=SCHEME,
    )  # fmt: skip
    return report


async def test_a_pre_commit_alert_and_its_links_are_in_the_loads_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = RuleGraph(ONTOLOGY)
    gate = _gate(_rule("pre_commit"), graph, monkeypatch, _finding)
    report = await _load(graph, gate, [_row("SYN-1", "SYN-2", 1)], "load-1")
    (alert,) = [n for n in graph.committed_nodes if n.type == "Alert"]
    links = [e for e in graph.committed_edges if e.type == "ALERTED_ON"]
    assert len(links) == 2
    # Held apart from what the change stream and the enrich stage read (they were recipe-written
    # elements only), and in the record, which is what a revert reads.
    assert alert.id in report.rule_node_ids
    assert {e.id for e in links} <= set(report.rule_created_edge_ids)
    assert alert.id not in report.created_node_ids
    assert not {e.id for e in links} & set(report.created_edge_ids + report.touched_edge_ids)
    assert report.merged_edge_ids == [] and report.rule_merged_edge_ids == []
    record = _record(report)
    assert alert.id in record.created_node_ids
    assert {e.id for e in links} <= set(record.created_edge_ids)
    assert {e.id for e in links} <= set(record.touched_edge_ids)
    assert alert.load_id == "load-1", "stamped with the load, as the record now says"


async def test_the_lists_the_stream_and_enrich_read_are_the_same_with_or_without_a_rules_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monitors must not see an `Alert` as a new ingest node: the report's `created_node_ids` and
    `touched_edge_ids` hold what the recipe wrote, whatever the rules add beside it."""
    plain_graph = RuleGraph(ONTOLOGY)
    quiet = _gate(_rule("pre_commit"), plain_graph, monkeypatch, _finding)
    quiet.rules = []
    plain = await _load(plain_graph, quiet, [_row("SYN-1", "SYN-2", 1)], "load-1")

    graph = RuleGraph(ONTOLOGY)
    gate = _gate(_rule("pre_commit"), graph, monkeypatch, _finding)
    ruled = await _load(graph, gate, [_row("SYN-1", "SYN-2", 1)], "load-1")
    assert [n for n in graph.committed_nodes if n.type == "Alert"], "the rule did write an alert"
    assert len(ruled.created_node_ids) == len(plain.created_node_ids)
    assert len(ruled.touched_edge_ids) == len(plain.touched_edge_ids)
    types = {n.id: n.type for n in graph.committed_nodes}
    assert "Alert" not in {types[i] for i in ruled.created_node_ids}
    alerted = {e.id for e in graph.committed_edges if e.type == "ALERTED_ON"}
    assert not alerted & set(ruled.touched_edge_ids)


async def test_what_a_finding_writes_alongside_its_alert_is_in_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = RuleGraph(ONTOLOGY)
    doc = NodeWrite(
        id=new_node_id(), type="Document", properties={"title": "screening hit"},
        provenance=_provenance(), handling=MARKING, created_by="loader-1", created_at=NOW,
    )  # fmt: skip

    def finding(rule: Any, deployer: Any, written: Any) -> Finding:
        endpoint = next(w.id for w in written if isinstance(w, NodeWrite) and w.type == "Endpoint")
        holds = EdgeWrite(
            id=new_edge_id(), type="HOLDS", source=endpoint, target=doc.id,
            provenance=_provenance(), handling=MARKING, created_by="loader-1", created_at=NOW,
        )  # fmt: skip
        return _finding(rule, deployer, written, pending=(doc, holds))

    gate = _gate(_rule("pre_commit"), graph, monkeypatch, finding)
    report = await _load(graph, gate, [_row("SYN-1", "SYN-2", 1)], "load-1")
    (holds,) = [e for e in graph.committed_edges if e.type == "HOLDS"]
    assert doc.id in report.rule_node_ids and holds.id in report.rule_created_edge_ids
    record = _record(report)
    assert doc.id in record.created_node_ids
    assert holds.id in record.created_edge_ids and holds.id in record.touched_edge_ids


async def test_a_pending_link_that_merges_into_another_loads_link_is_merged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = RuleGraph(ONTOLOGY)
    quiet = _gate(_rule("pre_commit"), graph, monkeypatch, lambda *a: (_ for _ in ()).throw(AssertionError))
    quiet.rules = []
    first = await _load(graph, quiet, [_row("SYN-1", "SYN-2", 1)], "load-1")
    (earlier,) = first.created_edge_ids

    def finding(rule: Any, deployer: Any, written: Any) -> Finding:
        # The pair the first load linked, which this load did not write: a pending link between
        # them is that link, and the store returns the first load's id.
        old = [n for n in graph.committed_nodes if n.type == "Endpoint"][:2]
        same = EdgeWrite(
            id=new_edge_id(), type="TRANSACTED", source=old[0].id, target=old[1].id,
            provenance=_provenance(), handling=MARKING, created_by="loader-1", created_at=NOW,
        )  # fmt: skip
        return _finding(rule, deployer, written, pending=(same,))

    gate = _gate(_rule("pre_commit"), graph, monkeypatch, finding)
    second = await _load(graph, gate, [_row("SYN-5", "SYN-6", 2)], "load-2")
    assert earlier in second.rule_merged_edge_ids
    assert earlier not in second.rule_created_edge_ids
    assert earlier in _record(second).merged_edge_ids
    assert earlier not in _record(second).created_edge_ids


async def test_a_pending_link_that_merges_into_the_loads_own_link_is_neither(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = RuleGraph(ONTOLOGY)

    def finding(rule: Any, deployer: Any, written: Any) -> Finding:
        a, b = [w for w in written if isinstance(w, NodeWrite) and w.type == "Endpoint"][:2]
        same = EdgeWrite(
            id=new_edge_id(), type="TRANSACTED", source=a.id, target=b.id,
            provenance=_provenance(), handling=MARKING, created_by="loader-1", created_at=NOW,
        )  # fmt: skip
        return _finding(rule, deployer, written, pending=(same,))

    gate = _gate(_rule("pre_commit"), graph, monkeypatch, finding)
    report = await _load(graph, gate, [_row("SYN-1", "SYN-2", 1)], "load-1")
    transacted = [e for e in graph.committed_edges if e.type == "TRANSACTED"]
    assert len(transacted) == 1
    assert transacted[0].id in report.created_edge_ids
    assert report.created_edge_ids.count(transacted[0].id) == 1
    assert report.merged_edge_ids == [] and report.rule_merged_edge_ids == []
    assert transacted[0].id not in report.rule_created_edge_ids
    assert _record(report).created_edge_ids.count(transacted[0].id) == 1


async def test_an_alert_raised_after_the_commit_is_added_to_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = RuleGraph(ONTOLOGY)
    gate = _gate(_rule("post_commit"), graph, monkeypatch, _finding)
    report = await _load(graph, gate, [_row("SYN-1", "SYN-2", 1)], "load-1")
    assert [n for n in graph.committed_nodes if n.type == "Alert"] == []

    told: dict[str, Any] = {}

    class Sink:
        async def rule_writes(self, load_id: str, **kwargs: Any) -> None:
            told.update(kwargs, load_id=load_id)

    notes = await post_commit_notes(gate, [], load_id="load-1", sink=Sink())  # type: ignore[arg-type]
    (alert,) = [n for n in graph.committed_nodes if n.type == "Alert"]
    assert told["load_id"] == "load-1" and told["node_ids"] == [alert.id]
    links = [e.id for e in graph.committed_edges if e.type == "ALERTED_ON"]
    assert sorted(told["created_edge_ids"]) == sorted(links) and told["merged_edge_ids"] == []
    assert notes and report.merged_edge_ids == []


async def test_a_post_commit_rule_that_writes_nothing_tells_the_record_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = RuleGraph(ONTOLOGY)
    gate = _gate(_rule("post_commit"), graph, monkeypatch, _finding)
    gate.rules = []

    class Sink:
        async def rule_writes(self, load_id: str, **kwargs: Any) -> None:
            raise AssertionError("nothing was written")

    assert await post_commit_notes(gate, [], load_id="load-1", sink=Sink()) == []  # type: ignore[arg-type]
