"""Starter questions (ADR-100 decision 8, Amendment 7): patterns that suit the case's types.

What a mistake would do, and the case that catches it:

- a question naming a type the case holds none of, or that the reader cannot see (the counts are
  the reader's own) (`test_a_type_the_case_holds_none_of_is_in_no_question`);
- a system link type such as `SAME_AS` offered as a question
  (`test_no_system_link_type_is_offered`);
- the order not the busiest link type first (`test_the_busiest_link_type_comes_first`);
- a list cut at six that says nothing of the rest (`test_what_is_not_shown_is_counted`);
- a question the compiler would refuse, or would send to the pinned-root path that needs a known
  node (`test_every_question_is_walked_from_its_first_variable`).
"""

from __future__ import annotations

from services.api.starter_questions import starter_questions, suited

from adapters.graph_arcadedb.access_filter import AccessFilter
from adapters.graph_arcadedb.builders import MatchBuilder
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.explore import TypeCounts

ONTOLOGY = load_default_ontology()
ENRON = TypeCounts(nodes={"Endpoint": 21955}, edges={"COMMUNICATED_WITH": 233935})
READER = Principal(id="r", clearance="OFFICIAL", org_unit="u", datasets=["enron"])


def test_the_enron_case_is_offered_its_chain() -> None:
    """Two who share two contacts is asked of one node instead (Amendment 7), so a case of
    addresses and the messages between them is offered one question."""
    offered = starter_questions(ENRON, ONTOLOGY)
    assert [q.question for q in offered.questions] == [
        "Endpoint → Endpoint → Endpoint, by “Communicated with” then “Communicated with”",
    ]
    assert offered.total == 1
    chain = offered.questions[0].pattern
    assert [(e.from_var, e.to_var) for e in chain.edges] == [("a", "b"), ("b", "c")]


def test_a_type_the_case_holds_none_of_is_in_no_question() -> None:
    counts = TypeCounts(nodes={"Person": 5, "Endpoint": 0}, edges={"USES": 3})
    assert suited(counts, ONTOLOGY) == []
    assert suited(TypeCounts(nodes={"Person": 5}, edges={}), ONTOLOGY) == []


def test_no_system_link_type_is_offered() -> None:
    """`SAME_AS` runs from `*` to `*` in the default ontology, which matches no type by name; the
    rule is the type's `system` flag, so the case gives it concrete ends."""
    concrete = ONTOLOGY.model_copy(
        update={
            "edge_types": [
                e.model_copy(update={"from_types": ["Person"], "to_types": ["Person"]})
                if e.name == "SAME_AS"
                else e
                for e in ONTOLOGY.edge_types
            ]
        }
    )
    counts = TypeCounts(nodes={"Person": 5}, edges={"SAME_AS": 9})
    assert suited(counts, concrete) == []
    # The case is real: an ordinary type with the same ends is offered.
    assert suited(TypeCounts(nodes={"Person": 5}, edges={"ASSOCIATE_OF": 9}), concrete) != []


def test_the_busiest_link_type_comes_first() -> None:
    counts = TypeCounts(
        nodes={"Person": 9, "Endpoint": 9},
        edges={"USES": 30, "COMMUNICATED_WITH": 3},  # the busier sorts after by name
    )
    ids = [q.id for q in suited(counts, ONTOLOGY)]
    assert ids == [
        "chain:USES:Person:Endpoint:COMMUNICATED_WITH:Endpoint",
        "chain:COMMUNICATED_WITH:Endpoint:Endpoint:COMMUNICATED_WITH:Endpoint",
    ]
    # A chain meets where one link type's end is the other's start.
    assert "chain:COMMUNICATED_WITH:Endpoint:Endpoint:USES:Endpoint" not in ids


def test_what_is_not_shown_is_counted() -> None:
    counts = TypeCounts(
        nodes={t.name: 5 for t in ONTOLOGY.entity_types},
        edges={e.name: 5 for e in ONTOLOGY.edge_types},
    )
    offered = starter_questions(counts, ONTOLOGY)
    assert len(offered.questions) == 6
    assert offered.total == len(suited(counts, ONTOLOGY)) > 6


def test_every_question_is_walked_from_its_first_variable() -> None:
    counts = TypeCounts(
        nodes={t.name: 5 for t in ONTOLOGY.entity_types},
        edges={e.name: 5 for e in ONTOLOGY.edge_types},
    )
    access = AccessFilter(load_uk_le_scheme())
    for question in suited(counts, ONTOLOGY):
        compiled = MatchBuilder(question.pattern)._render_single_chain(access, READER)
        assert compiled is not None, question.id
