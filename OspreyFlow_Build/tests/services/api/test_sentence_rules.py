"""A sentence rule on the load path (`spec/06_DECISIONS.md` ADR-133 decision 1, stage (b)), through
ADR-109's `RuleGate`: its drawn pattern read afresh as its author, its last blanks (severity, team,
scope, hold) carried out.

The stores the gate writes to are recorders here (the queue, the audit, the signature set); the
graph is `test_rule_sentences._Graph`, which applies the adapters' access predicate on every read,
grown to take the `Alert` node a case rule writes. Postgres's own reading of a deployment-wide
rule is `test_sentence_rule_store.py`'s.

What a mistake would do, and the case that catches it:
- an alert without the sentence's severity or team — `test_a_case_sentence_raises_its_alert_with_its_severity_and_team`;
- a "just me" alert reaching the case team or the case's graph — `test_a_just_me_sentence_alerts_its_author_alone_and_writes_nothing_to_the_graph`;
- a "hold" hit loading anyway — `test_a_hold_sentence_holds_a_hits_rows_and_raises_no_alert`;
- a rule run on a pattern no longer its author's — `test_a_sentence_whose_pattern_is_no_longer_its_authors_does_not_run`;
- a deployment-wide rule judging beyond the loading case's datasets — `test_a_deployment_wide_sentence_judges_within_the_loading_cases_datasets`.
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api.pattern_store import PatternNotFoundError
from services.api.rule_evaluation import RuleGate
from services.api.rule_sentences import compile_pattern

from schemas.domain import (
    Alert,
    Handling,
    NodeWrite,
    PatternQuery,
    Principal,
    SavedPattern,
    TypologyRule,
)
from schemas.sentences import RuleSentence, SentenceRuleParams
from tests.services.api.test_rule_sentences import (
    AUTHOR,
    CASE,
    NOW,
    ONTOLOGY,
    SCHEME,
    _Graph,
    _node,
    _provenance,
)


class _WritingGraph(_Graph):
    """`_Graph`, taking the `Alert` node and links a case rule writes, and recording them."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.written: list[Any] = []

    async def begin_transaction(self) -> str:
        return "tx-1"

    async def commit_transaction(self, tx: str) -> None:
        return None

    async def rollback_transaction(self, tx: str) -> None:
        return None

    async def upsert_nodes(self, nodes: list[Any], tx: str) -> list[str]:
        self.written.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: list[Any], tx: str) -> list[str]:
        self.written.extend(edges)
        return [e.id for e in edges]

    async def get_node(self, node_id: str, principal: Principal) -> Any:
        found = await self.get_nodes([node_id], principal)
        return found[0] if found else None

    async def get_edges(self, edge_ids: list[str], principal: Principal) -> list[Any]:
        return []


class _Recorder:
    def __init__(self) -> None:
        self.alerts: list[Alert] = []
        self.audit: list[dict[str, Any]] = []
        self.signatures: set[str] = set()
        self.held: list[Any] = []

    async def save(self, alert: Alert, handlings: Any = None) -> None:
        self.alerts.append(alert)

    async def record(self, **entry: Any) -> None:
        self.audit.append(entry)

    async def sismember(self, key: str, value: str) -> int:
        return int(value in self.signatures)

    async def sadd(self, key: str, value: str) -> int:
        self.signatures.add(value)
        return 1

    async def hold(self, rows: Any) -> None:
        self.held.extend(rows)


class _Patterns:
    def __init__(self, pattern: PatternQuery, owner: str = AUTHOR.id) -> None:
        self.pattern, self.owner = pattern, owner

    async def get_authorized(self, pattern_id: str, principal: Principal) -> SavedPattern:
        if principal.id != self.owner:
            raise PatternNotFoundError(pattern_id)
        return SavedPattern(id="s1", pattern_id=pattern_id, version=1, name="Rule", owner_id=self.owner,
                            created_at=NOW, definition=self.pattern)  # fmt: skip


def _rule(sentence: RuleSentence) -> TypologyRule:
    return TypologyRule(id="rule-s", investigation_id=CASE, owner_id=AUTHOR.id, name="Listed people",
                        created_at=NOW, trigger=sentence.runs,
                        params=SentenceRuleParams(pattern_id="pat-1", sentence=sentence))  # fmt: skip


def _gate(rule: TypologyRule, graph: _Graph, recorder: _Recorder, *, owner: str = AUTHOR.id,
          loader: Principal = AUTHOR, author: Principal = AUTHOR) -> RuleGate:  # fmt: skip
    assert isinstance(rule.params, SentenceRuleParams)

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return author if owner_id == author.id else None

    return RuleGate(rules=[rule], investigation_id=CASE, graph=graph, analytics=None, scheme=SCHEME,  # type: ignore[arg-type]
                    alert_store=recorder, audit=recorder, valkey=recorder, principal_for_owner=principal_for_owner,  # type: ignore[arg-type]
                    loader=loader, held_store=recorder, ontology=ONTOLOGY,  # type: ignore[arg-type]
                    patterns=_Patterns(compile_pattern(rule.params.sentence, ONTOLOGY), owner))  # type: ignore[arg-type]  # fmt: skip


LISTED = {"conditions": [{"op": "one_of", "property": "listing", "values": ["sanction", "pep"]}]}


def _write(node_id: str, marking: str = "OFFICIAL", **properties: Any) -> NodeWrite:
    return NodeWrite(id=node_id, type="Person", properties=properties, provenance=_provenance(),
                     handling=Handling(classification=marking, handling_code="P", owning_unit="unit-1",
                                       originator="unit-1"),
                     created_by="loader", created_at=NOW)  # fmt: skip


async def test_a_case_sentence_raises_its_alert_with_its_severity_and_team() -> None:
    sentence = RuleSentence.model_validate({"subject": "Person", **LISTED, "severity": "high", "team": "my_team"})
    graph, recorder = _WritingGraph([_node("p1", "Person", family_name="Okafor", listing="pep")]), _Recorder()
    gate = _gate(_rule(sentence), graph, recorder)
    notes = await gate.post_commit([], load_id="load-1", written=[_write("p1", listing="pep")])
    (alert,) = recorder.alerts
    assert (alert.rule_id, alert.typology, alert.severity, alert.team) == ("typology:rule-s", "sentence", "high", "unit-1")
    assert alert.referent_node_ids == ["p1"]
    assert alert.words is not None and alert.words.startswith("Okafor (Person)")
    assert "raise a high-severity alert for my team" in alert.words
    assert [w.type for w in graph.written if hasattr(w, "properties")][:1] == ["Alert"]
    assert notes == ["Rule “Listed people” raised 1 alert(s)."]
    # Once per finding: the same load again raises nothing new.
    await gate.post_commit([], load_id="load-2", written=[_write("p1", listing="pep")])
    assert len(recorder.alerts) == 1


async def test_a_just_me_sentence_alerts_its_author_alone_and_writes_nothing_to_the_graph() -> None:
    sentence = RuleSentence.model_validate({"subject": "Person", **LISTED, "scope": "just_me"})
    graph, recorder = _Graph([_node("p1", "Person", family_name="Okafor", listing="pep")]), _Recorder()
    await _gate(_rule(sentence), graph, recorder).post_commit([], load_id="load-1", written=[_write("p1")])
    (alert,) = recorder.alerts  # `_Graph` refuses every write: none was asked for
    assert (alert.rule_id, alert.typology, alert.team, alert.alert_node_id) == ("monitor:sentence:rule-s", None, None, None)
    assert alert.owner_id == AUTHOR.id
    assert not [e for e in recorder.audit if e["action"] == "alert_node_withheld"]


async def test_a_hold_sentence_holds_a_hits_rows_and_raises_no_alert() -> None:
    sentence = RuleSentence.model_validate({"subject": "Person", **LISTED, "runs": "pre_commit", "on_hit": "hold"})
    recorder = _Recorder()
    gate = _gate(_rule(sentence), _Graph([]), recorder)
    written = [_write("p1", listing="pep", family_name="A"), _write("p2", listing="adverse_media", family_name="B")]
    written[1] = written[1].model_copy(update={"provenance": written[1].provenance.model_copy(
        update={"sources": [written[1].provenance.sources[0].model_copy(update={"locator": "row 2"})]})})  # fmt: skip
    verdict = await gate.pre_commit([], "tx-1", load_id="load-1", unseen=None, written=written)
    assert sorted(verdict.hold) == [1]  # p1's row; p2 matches nothing
    rule, reason = verdict.hold[1]
    assert reason.startswith("it matched: A (Person)")
    assert verdict.findings == [] and recorder.alerts == []
    assert "held for review" in verdict.notes[0]


async def test_a_sentence_whose_pattern_is_no_longer_its_authors_does_not_run() -> None:
    sentence = RuleSentence.model_validate({"subject": "Person", **LISTED})
    recorder = _Recorder()
    gate = _gate(_rule(sentence), _Graph([_node("p1", "Person", listing="pep")]), recorder, owner="someone-else")
    notes = await gate.post_commit([], load_id="load-1", written=[_write("p1", listing="pep")])
    assert recorder.alerts == []
    assert "no longer its author's to read" in notes[0]
    assert [e["action"] for e in recorder.audit] == ["rule_failed"]


async def test_a_deployment_wide_sentence_judges_within_the_loading_cases_datasets() -> None:
    sentence = RuleSentence.model_validate({"subject": "Person", **LISTED, "scope": "deployment"})
    admin = Principal(id=AUTHOR.id, clearance="OFFICIAL", org_unit="unit-1", datasets=None)
    loader = AUTHOR.model_copy(update={"datasets": ["ds-case"]})
    seen: list[Principal] = []

    class _Watching(_WritingGraph):
        async def get_nodes(self, node_ids: Any, principal: Principal) -> Any:
            seen.append(principal)
            return await super().get_nodes(node_ids, principal)

    recorder = _Recorder()
    gate = _gate(_rule(sentence), _Watching([_node("p1", "Person", listing="pep")]), recorder,
                 loader=loader, author=admin)  # fmt: skip
    await gate.post_commit([], load_id="load-1", written=[_write("p1", listing="pep")])
    as_author = [p for p in seen if p.id == AUTHOR.id]  # the marking read is the service's own
    assert as_author and all(p.datasets == ["ds-case"] for p in as_author)
    (alert,) = recorder.alerts
    assert alert.dataset_id == "ds-case"


@pytest.mark.parametrize("scope", ["this_case", "deployment"])
def test_a_rule_says_the_sentence_runs_when_it_says(scope: str) -> None:
    sentence = RuleSentence.model_validate({"subject": "Person", "scope": scope})
    with pytest.raises(ValueError, match="the rule runs then"):
        TypologyRule(id="r", investigation_id=CASE, owner_id="a", name="n", created_at=NOW, trigger="pre_commit",
                     params=SentenceRuleParams(pattern_id="p", sentence=sentence))  # fmt: skip
