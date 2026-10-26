"""ADR-121: which conditions a pattern node may carry, checked against the ontology.

`PatternNode.where` maps a property of the node's type to the one text value it must equal. The
shape (equality, one string, at most three entries) is the model's own; this checks what only the
ontology knows. A condition is refused, by property name and never silently ignored (which would
widen the match to every node of the type), when:

- the node names no type, or a type the ontology does not hold (`no_type`, `unknown_type`);
- the type declares no such property (`unknown_property`; an identifier that is not also a declared
  property is not one — ADR-121 says indexed properties, and only a `properties` entry carries
  `indexed`);
- the property is `sensitivity: high` (`sensitive`), checked before indexing so a property that is
  both is refused for the reason that matters;
- the property is not `indexed` (`not_indexed`);
- the property is not text (`unsupported_type`): a value is one string, so a number, a date, a flag
  or a list has no equality this can state faithfully.

Both the Conduit's routes and the graph adapter call `check_pattern_conditions`: the route so the
analyst is told before anything is counted, the adapter so no caller of the port can compile a
condition the ontology refuses (access control and its neighbours live in the adapter, rule 3).
"""

from __future__ import annotations

from typing import Literal

from schemas.domain import OntologySchema, PatternQuery, PropertyType

Reason = Literal[
    "no_type", "unknown_type", "unknown_property", "sensitive", "not_indexed", "unsupported_type"
]

#: What a condition's one string value can faithfully state equality on.
_TEXT_TYPES = frozenset({PropertyType.STRING, PropertyType.ENUM})


class PatternConditionRefused(Exception):
    """A condition on a pattern node the ontology does not allow. Carries what a typed refusal
    needs: the variable, the property and the reason, as well as the words."""

    def __init__(self, *, var: str, property_name: str, reason: Reason, detail: str) -> None:
        super().__init__(detail)
        self.var = var
        self.property_name = property_name
        self.reason: Reason = reason
        self.detail = detail


def check_pattern_conditions(pattern: PatternQuery, ontology: OntologySchema) -> None:
    """Raises `PatternConditionRefused` for the first refused condition, nodes in drawing order and
    properties in name order; returns when every condition is allowed (or there are none)."""
    for node in pattern.nodes:
        for name in sorted(node.where):
            _check_one(node.var, node.entity_type, name, ontology)


def _check_one(var: str, entity_type: str | None, name: str, ontology: OntologySchema) -> None:
    def refuse(reason: Reason, detail: str) -> PatternConditionRefused:
        return PatternConditionRefused(var=var, property_name=name, reason=reason, detail=detail)

    if not entity_type:
        raise refuse(
            "no_type",
            f"a condition on {name!r} needs the node {var!r} to name its type, "
            "since a property belongs to a type",
        )
    type_def = ontology.entity_type(entity_type)
    if type_def is None:
        raise refuse("unknown_type", f"{entity_type!r} is not a type in the ontology")
    declared = next((p for p in type_def.properties if p.name == name), None)
    if declared is None:
        raise refuse(
            "unknown_property", f"{entity_type!r} declares no property {name!r} to match on"
        )
    if declared.sensitivity == "high":
        raise refuse(
            "sensitive",
            f"{entity_type}.{name} is marked sensitivity: high, so a pattern cannot match on it",
        )
    if not declared.indexed:
        raise refuse(
            "not_indexed",
            f"{entity_type}.{name} is not an indexed property, so a pattern cannot match on it",
        )
    if declared.type not in _TEXT_TYPES:
        raise refuse(
            "unsupported_type",
            f"{entity_type}.{name} is of type {declared.type.value!r}; a pattern condition "
            "matches one text value, so only a string or enumerated property can carry one",
        )
