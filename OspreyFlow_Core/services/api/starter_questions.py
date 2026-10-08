"""Starter questions (`06_DECISIONS.md` ADR-100 decision 8, Amendment 7): query-builder patterns
that suit the types a case holds, each run with one action.

Built from what the case's data holds (the kept `TypeCounts`, so only types the reader can see
shape a question) and the ontology's link types, never from a node: a question names types, so it
says nothing the counts beside it do not already say. Two shapes, in this order:

- *two who share two*: two records of one type linked by the same link type to the same two
  records of another, the ADR's own "people who wrote to two of the same people";
- *a chain*: a record linked to one linked to a third, by two link types that meet there.

The busiest link types first, ties by name. "Addresses sharing a name" is not one: a pattern has no
test on a property yet, which would need its own decision.
"""

from __future__ import annotations

from schemas.domain import EdgeTypeDef, OntologySchema, PatternEdge, PatternNode, PatternQuery
from schemas.explore import StarterQuestion, StarterQuestions, TypeCounts

#: How many are offered first; the rest are counted.
STARTERS_SHOWN = 6


def _link_name(edge_type: str) -> str:
    """As the Glass names a link type: "COMMUNICATED_WITH" is "Communicated with"."""
    return edge_type.replace("_", " ").lower().capitalize()


def _chain(
    first: EdgeTypeDef, source: str, middle: str, second: EdgeTypeDef, target: str
) -> StarterQuestion:
    return StarterQuestion(
        id=f"chain:{first.name}:{source}:{middle}:{second.name}:{target}",
        question=(
            f"{source} → {middle} → {target}, by “{_link_name(first.name)}” then "
            f"“{_link_name(second.name)}”"
        ),
        pattern=PatternQuery(
            nodes=[
                PatternNode(var="a", entity_type=source),
                PatternNode(var="b", entity_type=middle),
                PatternNode(var="c", entity_type=target),
            ],
            edges=[
                PatternEdge(edge_type=first.name, from_var="a", to_var="b"),
                PatternEdge(edge_type=second.name, from_var="b", to_var="c"),
            ],
        ),
    )


def suited(counts: TypeCounts, ontology: OntologySchema) -> list[StarterQuestion]:
    """Every starter question the case's types suit, in the order they are offered."""
    present = {name for name, n in counts.nodes.items() if n > 0}
    defined = {e.name: e for e in ontology.edge_types if not e.system}
    links = [
        defined[name]
        for name, n in sorted(counts.edges.items(), key=lambda item: (-item[1], item[0]))
        if n > 0 and name in defined
    ]
    chains = [
        _chain(first, source, middle, second, target)
        for first in links
        for second in links
        for source in first.from_types
        for middle in first.to_types
        for target in second.to_types
        if {source, middle, target} <= present and middle in second.from_types
    ]
    return chains


def starter_questions(
    counts: TypeCounts, ontology: OntologySchema, *, shown: int = STARTERS_SHOWN
) -> StarterQuestions:
    every = suited(counts, ontology)
    return StarterQuestions(questions=every[:shown], total=len(every))


__all__ = ["STARTERS_SHOWN", "starter_questions", "suited"]
