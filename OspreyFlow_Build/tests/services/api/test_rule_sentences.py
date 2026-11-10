"""Rules written as sentences (`spec/06_DECISIONS.md` ADR-133 decisions 1 and 3, stage (b)):
checked against the ontology, compiled to a drawn pattern and read back, judged and previewed as
the rule's author.

The analytics store is the real DuckDB adapter (its `event_frequency` is proven by the analytics
conformance suite). The graph is `_Graph` below, a stand-in for `GraphPort` that applies the same
access predicate the adapters do (`handling_readable`) to every node and link it reads, so a hidden
node is refused exactly as a store refuses it (rule 15: a fake models the refusals); it refuses
every write. It is not ArcadeDB, and ArcadeDB's own match and expand are proven by the graph
conformance suite, not here.

What a mistake would do, and the case that catches it:
- a sentence naming a type, property or link type the ontology does not declare, deployed —
  `test_a_sentence_naming_an_undeclared_property_is_refused_at_validation`,
  `test_a_sentence_naming_an_undeclared_link_type_is_refused_at_validation` and their neighbours;
- the sentence and its drawn pattern drifting into two rules —
  `test_a_sentence_and_its_drawn_pattern_compile_to_the_same_rule`;
- a frequency counted over what the author may not see —
  `test_a_rules_frequency_count_leaves_out_a_node_its_author_may_not_see`;
- a preview that says a hidden node is there —
  `test_a_preview_returns_no_count_or_example_that_reveals_a_filtered_node`;
- a preview counted in part past the limit — `test_a_preview_over_the_limit_returns_limit_exceeded`;
- a preview that writes — `test_a_preview_writes_nothing` (and the route's own case).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
import pytest
from services.api.rule_evaluation import handling_readable
from services.api.rule_sentences import (
    SentenceContext,
    SentenceRefused,
    check_sentence,
    compile_pattern,
    compile_sentence,
    judge_sentence,
    normalised,
    preview_sentence,
    sentence_of,
    sentence_words,
)
from services.api.working_set.models import LimitExceededError

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.analytics import EventRecord, GeometryRecord
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    ExpandRequest,
    Handling,
    Node,
    NodeWrite,
    PatternEdge,
    PatternNode,
    PatternQuery,
    Principal,
    Provenance,
    SourceRef,
    Subgraph,
    TypologyRule,
)
from schemas.sentences import RuleSentence, SentenceRuleParams

SCHEME = load_uk_le_scheme()
ONTOLOGY = load_deployment_ontology()
NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)
CASE = "case-sentences"

AUTHOR = Principal(id="author", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])  # deploy_rules: a right to have written a rule (ADR-146 Amendment 6 decision 13)
CLEARED = Principal(id="cleared", clearance="SECRET", org_unit="unit-1")


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(classification=classification, handling_code="P", owning_unit="unit-1",
                    originator="unit-1")  # fmt: skip


def _provenance() -> Provenance:
    return Provenance(state="asserted", first_seen=NOW,
                      sources=[SourceRef(document_id="doc-1", locator="row 1", excerpt_hash="h")])  # fmt: skip


def _node(node_id: str, entity_type: str, marking: str = "OFFICIAL", **properties: Any) -> Node:
    return Node(id=node_id, type=entity_type, properties=properties, provenance=_provenance(),
                handling=_handling(marking), audit=AuditStub(created_at=NOW, created_by="seed"))  # fmt: skip


def _edge(edge_id: str, edge_type: str, source: str, target: str, marking: str = "OFFICIAL") -> Edge:
    return Edge(id=edge_id, type=edge_type, source=source, target=target, provenance=_provenance(),
                handling=_handling(marking), audit=AuditStub(created_at=NOW, created_by="seed"))  # fmt: skip


class _Graph:
    """`GraphPort`'s reads over a few nodes and links, each read through the adapters' access
    predicate as the principal asking. Every write is refused: nothing here may write."""

    def __init__(self, nodes: Sequence[Node], edges: Sequence[Edge] = ()) -> None:
        self.nodes = {n.id: n for n in nodes}
        self.edges = list(edges)

    def _sees(self, principal: Principal, handling: Handling) -> bool:
        return handling_readable(SCHEME, principal, handling)

    def _visible(self, principal: Principal) -> dict[str, Node]:
        return {i: n for i, n in self.nodes.items() if self._sees(principal, n.handling)}

    def _links(self, principal: Principal) -> list[Edge]:
        seen = self._visible(principal)
        return [e for e in self.edges if self._sees(principal, e.handling)
                and e.source in seen and e.target in seen]  # fmt: skip

    async def get_nodes(self, node_ids: Sequence[str], principal: Principal) -> list[Node]:
        seen = self._visible(principal)
        return [seen[i] for i in node_ids if i in seen]

    def _bindings(self, pattern: PatternQuery, principal: Principal) -> tuple[set[str], set[str]]:
        seen = self._visible(principal)

        def fits(var: PatternNode, node: Node) -> bool:
            return ((var.entity_type is None or node.type == var.entity_type)
                    and (var.node_id is None or node.id == var.node_id)
                    and all(str(node.properties.get(k)) == v for k, v in var.where.items()))  # fmt: skip

        if not pattern.edges:
            (only,) = pattern.nodes
            return {i for i, n in seen.items() if fits(only, n)}, set()
        (link,) = pattern.edges
        by_var = {n.var: n for n in pattern.nodes}
        nodes: set[str] = set()
        edges: set[str] = set()
        for edge in self._links(principal):
            if edge.type == link.edge_type and fits(by_var[link.from_var], seen[edge.source]) \
                    and fits(by_var[link.to_var], seen[edge.target]):  # fmt: skip
                nodes.update({edge.source, edge.target})
                edges.add(edge.id)
        return nodes, edges

    async def match_count(self, pattern: PatternQuery, principal: Principal, *, ceiling: int) -> int:
        return min(len(self._bindings(pattern, principal)[0]), ceiling)

    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph:
        nodes, edges = self._bindings(pattern, principal)
        seen = self._visible(principal)
        return Subgraph(nodes=[seen[i] for i in sorted(nodes)][: pattern.limit],
                        edges=[e for e in self.edges if e.id in edges])  # fmt: skip

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        seen = self._visible(principal)
        reached, frontier, used = set(req.node_ids) & set(seen), set(req.node_ids) & set(seen), set()
        for _ in range(req.depth):
            nxt = set()
            for edge in self._links(principal):
                if req.edge_types and edge.type not in req.edge_types:
                    continue
                for a, b in ((edge.source, edge.target), (edge.target, edge.source)):
                    if a in frontier and b not in reached:
                        nxt.add(b)
                        used.add(edge.id)
            reached |= nxt
            frontier = nxt
        return Subgraph(nodes=[seen[i] for i in sorted(reached)],
                        edges=[e for e in self.edges if e.id in used])  # fmt: skip

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the graph was asked to {name}; a sentence only reads")


def _event(source: str, target: str, at: datetime, *, edge_type: str = "COMMUNICATED_WITH",
           marking: str = "OFFICIAL", **properties: Any) -> EventRecord:  # fmt: skip
    return EventRecord(event_id=f"ev-{source}-{target}-{at.isoformat()}-{marking}", edge_id=f"e-{source}-{target}",
                       edge_type=edge_type, source_id=source, target_id=target, occurred_at=at,
                       properties=properties, investigation_scope=CASE, handling=_handling(marking))  # fmt: skip


@pytest.fixture
async def analytics() -> AsyncIterator[AnalyticsDuckDBAdapter]:
    con = duckdb.connect(":memory:")
    create_events_table(con)
    create_geometries_table(con)
    yield AnalyticsDuckDBAdapter(con, SCHEME)
    con.close()


def _ctx(graph: _Graph, analytics: Any, **kwargs: Any) -> SentenceContext:
    return SentenceContext(graph=graph, analytics=analytics, investigation_scope=CASE,  # type: ignore[arg-type]
                           ontology=ONTOLOGY, **kwargs)  # fmt: skip


def _sentence(**kwargs: Any) -> RuleSentence:
    return RuleSentence.model_validate({"subject": "Person", **kwargs})


def _refused(sentence: RuleSentence) -> SentenceRefused:
    with pytest.raises(SentenceRefused) as refused:
        check_sentence(sentence, ONTOLOGY)
    return refused.value


# --- the sentence is checked against the ontology ------------------------------------------------


def test_a_sentence_naming_an_undeclared_property_is_refused_at_validation() -> None:
    refused = _refused(_sentence(conditions=[{"op": "equals", "property": "shoe_size", "value": "9"}]))
    assert (refused.refusal.blank, refused.refusal.reason) == ("conditions[0]", "unknown_property")
    assert "shoe_size" in refused.refusal.detail
    check_sentence(_sentence(conditions=[{"op": "equals", "property": "family_name", "value": "Okafor"}]), ONTOLOGY)


def test_a_sentence_naming_an_undeclared_link_type_is_refused_at_validation() -> None:
    linked = _refused(_sentence(relationship={"kind": "linked", "link_type": "KNOWS_SECRETLY"}))
    counted = _refused(RuleSentence(subject="Endpoint", frequency={"kind": "count", "link_type": "CALLED", "at_least": 3, "within_days": 7}))  # type: ignore[arg-type]
    system = _refused(_sentence(relationship={"kind": "linked", "link_type": "ALERTED_ON"}))
    assert {linked.refusal.reason, counted.refusal.reason, system.refusal.reason} == {"unknown_link_type"}
    assert (linked.refusal.blank, counted.refusal.blank) == ("relationship", "frequency")


def test_a_sentence_naming_an_undeclared_subject_or_other_type_is_refused() -> None:
    assert _refused(RuleSentence(subject="Spaceship")).refusal.reason == "unknown_type"
    other = _refused(_sentence(relationship={"kind": "within_steps", "steps": 2, "other_type": "Spaceship"}))
    assert other.refusal.reason == "unknown_type"


def test_a_choice_that_does_not_fit_what_it_names_is_refused() -> None:
    assert _refused(_sentence(conditions=[{"op": "above", "property": "family_name", "value": 3}])).refusal.reason == "unsupported_type"
    assert _refused(_sentence(conditions=[{"op": "equals", "property": "date_of_birth", "value": "1990-01-01"}])).refusal.reason == "sensitive"
    assert _refused(_sentence(conditions=[{"op": "one_of", "property": "listing", "values": ["sanction", "wanted"]}])).refusal.reason == "unknown_value"
    assert _refused(_sentence(relationship={"kind": "linked", "link_type": "TRANSACTED"})).refusal.reason == "link_not_for_subject"
    assert _refused(_sentence(relationship={"kind": "linked", "link_type": "USES", "other_type": "Document"})).refusal.reason == "link_not_for_other"
    assert _refused(_sentence(frequency={"kind": "count", "link_type": "USES", "at_least": 2, "within_days": 7})).refusal.reason == "not_events"
    assert _refused(RuleSentence(subject="Endpoint", frequency={"kind": "amount", "link_type": "TRANSACTED", "amount_property": "transaction_type", "over": 1, "within_days": 7})).refusal.reason == "unknown_property"  # type: ignore[arg-type]
    assert _refused(RuleSentence(subject="Endpoint", relationship={"kind": "on_screening_list"})).refusal.reason == "not_screened"  # type: ignore[arg-type]


def test_the_sentences_blanks_agree_before_the_ontology_is_read() -> None:
    with pytest.raises(ValueError, match="only a rule that runs before commit can hold"):
        _sentence(on_hit="hold")
    with pytest.raises(ValueError, match="runs after commit"):
        _sentence(runs="pre_commit", relationship={"kind": "linked", "link_type": "USES"})
    with pytest.raises(ValueError, match="for you alone"):
        _sentence(scope="just_me", team="my_team")
    with pytest.raises(ValueError, match="one condition"):
        _sentence(conditions=[{"op": "equals", "property": "family_name", "value": "A"},
                              {"op": "one_of", "property": "family_name", "values": ["A", "B"]}])  # fmt: skip


# --- the sentence and its drawn pattern are one rule ---------------------------------------------

ROUND_TRIP = _sentence(
    conditions=[{"op": "one_of", "property": "listing", "values": ["sanction", "pep"]},
                {"op": "equals", "property": "family_name", "value": "Okafor"}],
    relationship={"kind": "linked", "link_type": "USES", "other_type": "Endpoint"},
    frequency={"kind": "count", "link_type": "PRESENT_AT", "at_least": 3, "within_days": 7},
    severity="high",
)  # fmt: skip


def test_a_sentence_and_its_drawn_pattern_compile_to_the_same_rule() -> None:
    compiled = compile_pattern(ROUND_TRIP, ONTOLOGY)
    assert compiled.nodes[0].model_dump() == {"var": "subject", "entity_type": "Person", "node_id": None,
                                              "where": {"family_name": "Okafor"}}  # fmt: skip
    assert [e.model_dump() for e in compiled.edges] == [{"edge_type": "USES", "from_var": "subject", "to_var": "other"}]
    # The same rule drawn by hand in the query builder: other names, the other node drawn first.
    drawn = PatternQuery(
        nodes=[PatternNode(var="phone", entity_type="Endpoint"),
               PatternNode(var="p", entity_type="Person", where={"family_name": "Okafor"})],
        edges=[PatternEdge(edge_type="USES", from_var="p", to_var="phone")],
    )  # fmt: skip
    read = sentence_of(drawn, ROUND_TRIP, ONTOLOGY)
    assert read == normalised(ROUND_TRIP)
    assert compile_pattern(read, ONTOLOGY) == compiled
    assert sentence_of(compiled, ROUND_TRIP, ONTOLOGY) == normalised(ROUND_TRIP)


def test_the_drawn_pattern_edited_in_the_query_builder_is_the_sentence_changed() -> None:
    edited = compile_pattern(ROUND_TRIP, ONTOLOGY)
    edited.nodes[0].where = {"family_name": "Adeyemi", "given_names": "Sam"}
    read = sentence_of(edited, ROUND_TRIP, ONTOLOGY)
    assert [(c.op, c.property) for c in read.conditions] == [
        ("equals", "family_name"), ("equals", "given_names"), ("one_of", "listing")]  # fmt: skip
    unlinked = edited.model_copy(update={"nodes": edited.nodes[:1], "edges": []})
    assert sentence_of(unlinked, ROUND_TRIP, ONTOLOGY).relationship is None
    assert sentence_of(unlinked, ROUND_TRIP, ONTOLOGY).frequency == ROUND_TRIP.frequency


def test_a_drawn_pattern_no_sentence_can_say_is_refused_in_words() -> None:
    two_links = PatternQuery(
        nodes=[PatternNode(var="a", entity_type="Person"), PatternNode(var="b", entity_type="Endpoint"),
               PatternNode(var="c", entity_type="Endpoint")],
        edges=[PatternEdge(edge_type="USES", from_var="a", to_var="b"),
               PatternEdge(edge_type="COMMUNICATED_WITH", from_var="b", to_var="c")],
    )  # fmt: skip
    pinned = PatternQuery(nodes=[PatternNode(var="subject", entity_type="Person", node_id="n1")], edges=[])
    for pattern in (two_links, pinned):
        with pytest.raises(SentenceRefused) as refused:
            sentence_of(pattern, ROUND_TRIP, ONTOLOGY)
        assert refused.value.refusal.reason == "not_a_sentence"


def test_the_sentence_reads_as_words() -> None:
    words = compile_sentence(ROUND_TRIP, ONTOLOGY).words
    assert words.startswith("When a Person whose family name is Okafor and listing is one of sanction, pep")
    assert ", is linked by “Uses” to an Endpoint, " in words
    assert "3 or more times by “Present at” within 7 day(s)" in words
    assert words.endswith("raise a high-severity alert for the case team, after each load commits.")


# --- judged and previewed as the author ----------------------------------------------------------


def _calls(subject: str, other: str, days: Sequence[float], marking: str = "OFFICIAL") -> list[EventRecord]:
    return [_event(subject, other, NOW - timedelta(days=20 - d), marking=marking) for d in days]


async def test_a_rules_frequency_count_leaves_out_a_node_its_author_may_not_see(analytics: Any) -> None:
    """ADR-133: the phone's third call in a week was to a SECRET phone, over a SECRET link. Its
    author, cleared to OFFICIAL, must count two and raise nothing; one cleared to SECRET counts
    three. A SECRET phone with three OFFICIAL-marked calls is not a subject at all."""
    graph = _Graph([_node("p1", "Endpoint", value_normalised="+447700900001"),
                    _node("p2", "Endpoint", value_normalised="+447700900002"),
                    _node("hidden", "Endpoint", "SECRET", value_normalised="+447700900666"),
                    _node("hidden-subject", "Endpoint", "SECRET", value_normalised="+447700900777")])  # fmt: skip
    await analytics.load_events([*_calls("p1", "p2", [0, 1]), *_calls("p1", "hidden", [2], "SECRET"),
                                 *_calls("hidden-subject", "hidden", [0, 1, 2])])  # fmt: skip
    sentence = RuleSentence(subject="Endpoint", frequency={"kind": "count", "link_type": "COMMUNICATED_WITH", "at_least": 3, "within_days": 7})  # type: ignore[arg-type]
    seen = await preview_sentence(sentence, AUTHOR, _ctx(graph, analytics), now=NOW)
    cleared = await preview_sentence(sentence, CLEARED, _ctx(graph, analytics), now=NOW)
    assert seen.would_raise == 0 and seen.examples == []
    assert {e.node_id for e in cleared.examples} == {"p1", "hidden", "hidden-subject"}


async def test_a_preview_returns_no_count_or_example_that_reveals_a_filtered_node(analytics: Any) -> None:
    """The same preview over a store holding a hidden match and over one without it answers alike."""
    visible = [_node("v1", "Person", family_name="Okafor", listing="pep")]
    hidden = _node("h1", "Person", "SECRET", family_name="Okafor", given_names="Hidden", listing="pep")
    sentence = _sentence(conditions=[{"op": "equals", "property": "family_name", "value": "Okafor"},
                                     {"op": "equals", "property": "listing", "value": "pep"}])  # fmt: skip
    with_hidden = await preview_sentence(sentence, AUTHOR, _ctx(_Graph([*visible, hidden]), analytics), now=NOW)
    without = await preview_sentence(sentence, AUTHOR, _ctx(_Graph(visible), analytics), now=NOW)
    cleared = await preview_sentence(sentence, CLEARED, _ctx(_Graph([*visible, hidden]), analytics), now=NOW)
    assert with_hidden == without
    assert (with_hidden.would_raise, [e.node_id for e in with_hidden.examples]) == (1, ["v1"])
    assert "Hidden" not in with_hidden.model_dump_json()
    assert cleared.would_raise == 2


async def test_a_preview_over_the_limit_returns_limit_exceeded(analytics: Any) -> None:
    people = [_node(f"v{i}", "Person", family_name="Okafor") for i in range(3)]
    sentence = _sentence(conditions=[{"op": "equals", "property": "family_name", "value": "Okafor"}])
    with pytest.raises(LimitExceededError) as over:
        await preview_sentence(sentence, AUTHOR, _ctx(_Graph(people), analytics), now=NOW, cap=2)
    assert over.value.detail.model_dump()["error"] == "limit_exceeded"
    assert (over.value.detail.cap, over.value.detail.would_be) == (2, 3)
    # Counted as the author: hidden matches never tip a preview over the limit.
    hidden = [_node(f"h{i}", "Person", "SECRET", family_name="Okafor") for i in range(5)]
    within = await preview_sentence(sentence, AUTHOR, _ctx(_Graph([*people[:2], *hidden]), analytics), now=NOW, cap=2)
    assert within.would_raise == 2


async def test_a_preview_writes_nothing(analytics: Any) -> None:
    graph = _Graph([_node("v1", "Person", family_name="Okafor")])
    before = analytics._con.execute("SELECT COUNT(*) FROM events").fetchone()
    preview = await preview_sentence(_sentence(), AUTHOR, _ctx(graph, analytics), now=NOW)
    assert preview.would_raise == 1
    assert analytics._con.execute("SELECT COUNT(*) FROM events").fetchone() == before
    with pytest.raises(AssertionError, match="a sentence only reads"):
        await graph.upsert_nodes([], AUTHOR)  # the stand-in refuses every write it is asked for


async def test_amounts_first_times_hotlists_areas_and_steps_are_judged_as_the_author(analytics: Any) -> None:
    area = {"name": "the port", "points": [{"lon": 0, "lat": 0}, {"lon": 1, "lat": 0}, {"lon": 1, "lat": 1}, {"lon": 0, "lat": 1}]}
    graph = _Graph(
        [_node("a1", "Endpoint", value_normalised="acct-1"), _node("a2", "Endpoint", value_normalised="acct-2"),
         _node("person", "Person", family_name="Okafor"), _node("place", "Location", name="Quay", geometry_ref="g-in"),
         _node("far", "Location", name="Far", geometry_ref="g-out"), _node("other", "Person", family_name="Smith"),
         _node("phone", "Endpoint", value_normalised="+447700900310")],
        [_edge("x1", "PRESENT_AT", "person", "place"), _edge("x2", "PRESENT_AT", "other", "far"),
         _edge("x3", "USES", "other", "phone")],
    )  # fmt: skip
    await analytics.load_geometries([
        GeometryRecord(geometry_ref="g-in", version=1, lon=0.5, lat=0.5, handling=_handling()),
        GeometryRecord(geometry_ref="g-out", version=1, lon=5, lat=5, handling=_handling())])  # fmt: skip
    await analytics.load_events([
        _event("a1", "a2", NOW - timedelta(days=10), edge_type="TRANSACTED", amount=6000),
        _event("a1", "a2", NOW - timedelta(days=9), edge_type="TRANSACTED", amount=5000),
        _event("a2", "a9", NOW - timedelta(days=200), edge_type="TRANSACTED", amount=10)])  # fmt: skip
    ctx = _ctx(graph, analytics, hotlisted=frozenset({"+447700900310"}))

    async def raised(sentence: RuleSentence) -> list[str]:
        return [e.node_id for e in (await preview_sentence(sentence, AUTHOR, ctx, now=NOW)).examples]

    amount = {"kind": "amount", "link_type": "TRANSACTED", "amount_property": "amount", "over": 10000, "within_days": 7}
    assert await raised(RuleSentence(subject="Endpoint", frequency=amount)) == ["a1", "a2"]  # either end  # type: ignore[arg-type]
    assert await raised(RuleSentence(subject="Endpoint", frequency={**amount, "over": 12000})) == []  # type: ignore[arg-type]
    first = {"kind": "first_time", "link_type": "TRANSACTED"}
    assert await raised(RuleSentence(subject="Endpoint", frequency=first)) == ["a1"]  # type: ignore[arg-type]
    assert await raised(RuleSentence(subject="Endpoint", relationship={"kind": "on_hotlist"})) == ["phone"]  # type: ignore[arg-type]
    assert await raised(_sentence(relationship={"kind": "at_location", "link_type": "PRESENT_AT", "area": area})) == ["person"]
    assert await raised(RuleSentence(subject="Location", conditions=[{"op": "within_area", "property": "geometry_ref", "area": area}])) == ["place"]  # type: ignore[list-item]
    assert await raised(_sentence(relationship={"kind": "within_steps", "steps": 1, "other_type": "Endpoint"})) == ["other"]


def _rule(sentence: RuleSentence, *, max_matches: int = 200) -> TypologyRule:
    return TypologyRule(id="rule-1", investigation_id=CASE, owner_id=AUTHOR.id, name="Sentence", created_at=NOW,
                        trigger=sentence.runs,
                        params=SentenceRuleParams(pattern_id="pat-1", sentence=sentence, max_matches=max_matches))  # fmt: skip


def _write(node_id: str, entity_type: str, marking: str = "OFFICIAL", **properties: Any) -> NodeWrite:
    return NodeWrite(id=node_id, type=entity_type, properties=properties, provenance=_provenance(),
                     handling=_handling(marking), created_by="loader", created_at=NOW)  # fmt: skip


async def test_as_data_loads_a_link_is_matched_pinned_to_each_subject_as_the_author(analytics: Any) -> None:
    sentence = _sentence(relationship={"kind": "linked", "link_type": "USES", "other_type": "Endpoint"})
    graph = _Graph([_node("p1", "Person", family_name="A"), _node("p2", "Person", family_name="B"),
                    _node("p3", "Person", family_name="C"), _node("e1", "Endpoint", value_normalised="1"),
                    _node("e3", "Endpoint", "SECRET", value_normalised="3")],
                   [_edge("u1", "USES", "p1", "e1"), _edge("u3", "USES", "p3", "e3")])  # fmt: skip
    written = [_write("p1", "Person"), _write("p2", "Person"), _write("p3", "Person"),
               EdgeWrite(id="u1", type="USES", source="p1", target="e1", provenance=_provenance(),
                         handling=_handling(), created_by="loader", created_at=NOW)]  # fmt: skip
    hits = await judge_sentence(_rule(sentence), AUTHOR, written, [], _ctx(graph, analytics),
                                pattern=compile_pattern(sentence, ONTOLOGY), scheme=SCHEME, now=NOW)  # fmt: skip
    assert [h.node.id for h in hits] == ["p1"]  # p3's only link is to a SECRET phone


async def test_before_commit_a_subject_is_judged_as_written_and_only_if_the_author_may_read_it(analytics: Any) -> None:
    sentence = _sentence(conditions=[{"op": "one_of", "property": "listing", "values": ["sanction", "pep"]}],
                         runs="pre_commit", on_hit="hold")  # fmt: skip
    written = [_write("n1", "Person", listing="pep", family_name="A"),
               _write("n2", "Person", "SECRET", listing="pep", family_name="B"),
               _write("n3", "Person", listing="adverse_media", family_name="C")]  # fmt: skip
    hits = await judge_sentence(_rule(sentence), AUTHOR, written, [], _ctx(_Graph([]), analytics),
                                pattern=compile_pattern(sentence, ONTOLOGY), scheme=SCHEME, now=NOW)  # fmt: skip
    assert [h.node.id for h in hits] == ["n1"]


async def test_a_load_touching_more_subjects_than_the_rule_judges_is_refused_not_judged_in_part(analytics: Any) -> None:
    sentence = _sentence(runs="pre_commit")
    written = [_write(f"n{i}", "Person", family_name="A") for i in range(3)]
    with pytest.raises(RuntimeError, match="not judged on part of them"):
        await judge_sentence(_rule(sentence, max_matches=2), AUTHOR, written, [], _ctx(_Graph([]), analytics),
                             pattern=compile_pattern(sentence, ONTOLOGY), scheme=SCHEME, now=NOW)  # fmt: skip


def test_the_words_name_the_audience_and_the_hold() -> None:
    held = _sentence(runs="pre_commit", on_hit="hold", scope="deployment")
    assert sentence_words(held, ONTOLOGY).endswith(
        "raise a medium-severity alert for every case's team, before each load commits, holding its rows for review.")
    assert "for me alone" in sentence_words(_sentence(scope="just_me"), ONTOLOGY)
