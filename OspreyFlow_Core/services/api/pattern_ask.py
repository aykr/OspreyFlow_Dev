"""Ask to search (`06_DECISIONS.md` ADR-129 decision 2, Brief 3 item E3): an analyst types a
question in the query builder and the model proposes a pattern. Nothing runs.

**What the model is given.** Only the case's vocabulary (`vocabulary_of`: the entity types, the
link types an analyst may draw with their ends and direction, and the indexed text properties a
condition may name with their enum values, ADR-121) and the analyst's question. Never a node id, a
link id, Gremlin or a source identifier (rule 7). It answers under constrained decoding against a
JSON Schema built from that vocabulary, so a type or a link outside it cannot be written; the
Conduit checks the answer anyway (`PatternProposer`), because a schema is not the only line of
defence and a fake model is not constrained.

**What the Conduit validates.** The type of every node, the type of every link and that the link
joins the types it is drawn between (the ontology's own ends, either way for an undirected link),
the variables, and every condition by `ontology.pattern_where.check_pattern_conditions` (ADR-121),
the routes' own rule. Anything else, and anything the query builder cannot draw (absence, ranges:
a condition is one string equal to a property's value), is refused as `could_not_express`, typed,
and the panel says so (`CouldNotExpress`). A pattern the compiler cannot run (an open second root)
is refused the same way when the preview's count is asked.

**Placeholders (rule 3).** "The principal" and "the selected person" are `$selected_1` and so on.
They are numbered over the analyst's selection *as they may see it* (`visible_membership`, the
same projection every read applies): an id they may not see, and an id that does not exist, are
dropped before the numbering and the prompt, so a hidden node and a made-up one produce the same
prompt, the same refusal and the same words. The model is told only how many there are. The
Conduit puts the real ids in after validation, and the pattern it returns carries them as the
builder's pinned nodes.

**What the analyst gets.** The pattern, a one-line explanation and the count from
`preview_pattern`, the preview route's own function (`PatternProposal`). The run is the existing
run route (rules 3 and 4). A proposed pattern is not a fact, and nothing here writes (rule 5).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ontology.pattern_where import PatternConditionRefused, check_pattern_conditions
from ports.graph import GraphPort
from ports.model import ModelPort
from schemas.domain import (
    PATTERN_WHERE_MAX,
    OntologySchema,
    PatternEdge,
    PatternNode,
    PatternQuery,
    Principal,
    PropertyType,
)
from schemas.model import ExtractionRequest

from .patterns import preview_pattern
from .working_set.service import WorkingSetService

#: A search question is a sentence, not a document: the extraction model reads it with the
#: vocabulary inside its context.
MAX_QUESTION_CHARS = 1_000
#: How many ids the Glass may send: what is selected on the canvas.
MAX_SELECTION = 2_000
#: Past this the model's own explanation is not "one line" and the pattern's is shown instead.
MAX_EXPLANATION_CHARS = 240

_VARIABLE = re.compile(r"^[a-z]$")
_PLACEHOLDER = re.compile(r"^\$selected_([1-9][0-9]*)$")
_NODE_KEYS = frozenset({"var", "entity_type", "where", "reference"})
_EDGE_KEYS = frozenset({"edge_type", "from_var", "to_var"})
_CONDITION_KEYS = frozenset({"property", "value"})

Reason = Literal[
    "model_declined",
    "no_pattern",
    "malformed",
    "repeated_variable",
    "unknown_type",
    "unknown_link",
    "unknown_variable",
    "link_ends",
    "condition_refused",
    "unresolved_reference",
    "not_runnable",
]

_DETAIL: dict[str, str] = {
    "model_declined": (
        "The question cannot be put in this case's vocabulary of types, links and properties."
    ),
    "no_pattern": "The model proposed no pattern.",
    "malformed": "The model's answer was not a pattern the query builder can draw.",
    "repeated_variable": "The model's pattern named two nodes with the same variable.",
    "unknown_type": "The pattern names a type that is not in this case's vocabulary.",
    "unknown_link": "The pattern names a link type that is not in this case's vocabulary.",
    "unknown_variable": "The pattern joins a node that it does not draw.",
    "link_ends": "The pattern draws a link between types that the link does not join.",
    "unresolved_reference": (
        "The question refers to a selected item and none is selected that this case can use."
    ),
    "not_runnable": (
        "The pattern joins separate parts with no known node to start from, so the query builder "
        "cannot run it."
    ),
}


class AskToSearchRequest(BaseModel):
    """The question and what the analyst has selected on the canvas. The ids are only ever resolved
    to nodes the analyst may see; the model never receives them."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    selected_node_ids: list[str] = Field(default_factory=list, max_length=MAX_SELECTION)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("the question is blank")
        return value


class PatternProposal(BaseModel):
    """What ask to search answers, before anything runs: the pattern for the builder to draw, one
    line saying what it finds, and the preview's own count (a floor at its ceiling)."""

    pattern: PatternQuery
    explanation: str
    estimated_count: int
    is_floor: bool


class CouldNotExpressBody(BaseModel):
    """The typed refusal the panel shows: it could not express the question."""

    error: Literal["could_not_express"] = "could_not_express"
    reason: Reason
    detail: str


class CouldNotExpress(Exception):
    """The question, or the model's answer to it, cannot be drawn as a pattern in this case's
    vocabulary. The words are fixed per reason (never the model's own), so a refusal says nothing
    about what the analyst may not see."""

    def __init__(self, reason: Reason, detail: str | None = None) -> None:
        self.reason: Reason = reason
        self.detail = detail if detail is not None else _DETAIL[reason]
        super().__init__(self.detail)

    def body(self) -> CouldNotExpressBody:
        return CouldNotExpressBody(reason=self.reason, detail=self.detail)


# --- the vocabulary -------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkVocabulary:
    name: str
    from_types: tuple[str, ...]
    to_types: tuple[str, ...]
    directed: bool

    def joins(self, source: str, target: str) -> bool:
        """Whether a link of this type may run `source` to `target`, either way when undirected.
        `*` is any type, as the ontology writes it."""

        def holds(types: tuple[str, ...], kind: str) -> bool:
            return "*" in types or kind in types

        forward = holds(self.from_types, source) and holds(self.to_types, target)
        backward = holds(self.from_types, target) and holds(self.to_types, source)
        return forward or (not self.directed and backward)


@dataclass(frozen=True)
class PropertyVocabulary:
    entity_type: str
    name: str
    values: tuple[str, ...] | None


@dataclass(frozen=True)
class Vocabulary:
    entity_types: tuple[str, ...]
    links: tuple[LinkVocabulary, ...]
    properties: tuple[PropertyVocabulary, ...]

    def text(self) -> str:
        lines = ["Entity types:"]
        lines += [f"- {name}" for name in self.entity_types]
        lines += ["", "Link types (a directed link runs from the first types to the second):"]
        for link in self.links:
            ends = f"{_types(link.from_types)} -> {_types(link.to_types)}"
            if not link.directed:
                ends = f"{_types(link.from_types)} <-> {_types(link.to_types)}"
            lines.append(f"- {link.name}: {ends} ({'directed' if link.directed else 'either way'})")
        lines += ["", "Properties a node may be required to equal (one exact value):"]
        for prop in self.properties:
            allowed = f", one of: {', '.join(prop.values)}" if prop.values else ""
            lines.append(f"- {prop.entity_type}.{prop.name}{allowed}")
        return "\n".join(lines)

    def condition_properties(self) -> list[str]:
        return sorted({p.name for p in self.properties})


def _types(types: tuple[str, ...]) -> str:
    return "any type" if "*" in types else ", ".join(types)


def vocabulary_of(ontology: OntologySchema) -> Vocabulary:
    """The case's vocabulary: every entity type; every link type an analyst may draw (not a system
    link such as `SAME_AS`, and not an analyst's proposal's own storage label); and the properties a
    condition may name, by ADR-121 Amendment 1's rule: indexed, text (a string or an enum), and not
    `sensitivity: high`. The ontology's own, never a count of what the case holds, so what is
    offered says nothing about what an analyst may not see (rule 3)."""
    properties = [
        PropertyVocabulary(
            entity_type=entity.name,
            name=prop.name,
            values=tuple(prop.values) if prop.type is PropertyType.ENUM and prop.values else None,
        )
        for entity in ontology.entity_types
        for prop in entity.properties
        if prop.indexed
        and prop.sensitivity != "high"
        and prop.type in (PropertyType.STRING, PropertyType.ENUM)
    ]
    return Vocabulary(
        entity_types=tuple(e.name for e in ontology.entity_types),
        links=tuple(
            LinkVocabulary(
                name=e.name,
                from_types=tuple(e.from_types),
                to_types=tuple(e.to_types),
                directed=e.directed,
            )
            for e in ontology.edge_types
            if not e.system and not e.hidden
        ),
        properties=tuple(properties),
    )


# --- what the model is sent -----------------------------------------------------------------

_INSTRUCTIONS = (
    "You turn an analyst's question into a search pattern over a graph of entities and links. "
    "Use only the entity types, link types and properties listed below; never invent one. A "
    "pattern is a set of nodes, each with a one-letter variable and an entity type, and a set "
    "of links, each with a link type, from one variable to another; keep the direction the list "
    "gives a directed link. To require a node to have a given value (a name, say), add a "
    "condition on one listed property of its type, with the value as the analyst wrote it. To "
    "ask for two or more different things of the same type, give each its own variable. If the "
    "question cannot be stated with the listed types, links and properties (it asks who is "
    "guilty, predicts what will happen, asks for something that is absent or missing, or needs "
    "a number, date or range), set can_express to false and leave nodes and edges empty. "
    "Otherwise set can_express to true and write explanation: one short sentence, in plain "
    "words, saying what the pattern finds."
)


def _selection_instruction(placeholders: int) -> str:
    if placeholders == 0:
        return (
            "The analyst has selected nothing, so no node may be given a reference. If the "
            "question needs something they selected, set can_express to false."
        )
    names = ", ".join(f"$selected_{i}" for i in range(1, placeholders + 1))
    return (
        f"The analyst has selected {placeholders} item(s), which you may refer to as {names}. When "
        "the question means something they selected ('the principal', 'the selected person', 'the "
        "number'), set reference on that node to one of those, and give the node its type. You are "
        "not told what the selected items are."
    )


def proposal_schema(vocabulary: Vocabulary, placeholders: int) -> dict[str, Any]:
    """The JSON Schema the model's answer is decoded against. A type or link outside the
    vocabulary, a node id, or a reference past the selection cannot be written under it."""
    node_properties: dict[str, Any] = {
        "var": {"type": "string", "pattern": "^[a-z]$"},
        "entity_type": {"type": "string", "enum": list(vocabulary.entity_types)},
    }
    conditionable = vocabulary.condition_properties()
    if conditionable:
        node_properties["where"] = {
            "type": "array",
            "maxItems": PATTERN_WHERE_MAX,
            "items": {
                "type": "object",
                "properties": {
                    "property": {"type": "string", "enum": conditionable},
                    "value": {"type": "string", "minLength": 1},
                },
                "required": ["property", "value"],
                "additionalProperties": False,
            },
        }
    if placeholders:
        node_properties["reference"] = {
            "type": "string",
            "enum": [f"$selected_{i}" for i in range(1, placeholders + 1)],
        }
    edges: dict[str, Any]
    if vocabulary.links:
        edges = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "edge_type": {
                        "type": "string",
                        "enum": [link.name for link in vocabulary.links],
                    },
                    "from_var": {"type": "string", "pattern": "^[a-z]$"},
                    "to_var": {"type": "string", "pattern": "^[a-z]$"},
                },
                "required": ["edge_type", "from_var", "to_var"],
                "additionalProperties": False,
            },
        }
    else:
        edges = {"type": "array", "maxItems": 0, "items": {}}
    return {
        "type": "object",
        "properties": {
            "can_express": {"type": "boolean"},
            "explanation": {"type": "string"},
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": node_properties,
                    "required": ["var", "entity_type"],
                    "additionalProperties": False,
                },
            },
            "edges": edges,
        },
        "required": ["can_express", "explanation", "nodes", "edges"],
        "additionalProperties": False,
    }


# --- what the Conduit accepts ---------------------------------------------------------------


@dataclass(frozen=True)
class Proposal:
    """A validated pattern whose pinned nodes still hold their placeholders (`$selected_1`), and
    the model's one-line explanation; the golden set scores it as it is, the service resolves it."""

    pattern: PatternQuery
    explanation: str
    model: str


def describe_pattern(pattern: PatternQuery) -> str:
    """One line in words, written from the pattern itself: what is shown when the model's own
    explanation is missing or is not one short line."""
    kind = {n.var: n.entity_type or "node" for n in pattern.nodes}
    touched = {v for e in pattern.edges for v in (e.from_var, e.to_var)}
    parts = [f"{n.var}: {kind[n.var]}" for n in pattern.nodes if n.var not in touched]
    parts += [
        f"{e.from_var}: {kind[e.from_var]} {e.edge_type} {e.to_var}: {kind[e.to_var]}"
        for e in pattern.edges
    ]
    extras = [f"{n.var} is a selected item" for n in pattern.nodes if n.node_id]
    extras += [f"{n.var}.{k} is {v}" for n in pattern.nodes for k, v in sorted(n.where.items())]
    text = "Finds " + "; ".join(parts)
    return f"{text} where {', '.join(extras)}." if extras else f"{text}."


def _one_line(text: object, pattern: PatternQuery) -> str:
    line = " ".join(text.split()) if isinstance(text, str) else ""
    if not line or len(line) > MAX_EXPLANATION_CHARS:
        return describe_pattern(pattern)
    return line


def _record(value: object, allowed: frozenset[str]) -> dict[str, Any]:
    """A JSON object holding only keys the schema offered: a key it did not is not a pattern the
    builder can draw (a node id, say, which the model was never given)."""
    if not isinstance(value, dict) or not set(value) <= allowed:
        raise CouldNotExpress("malformed")
    return value


def _conditions(raw: object) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise CouldNotExpress("malformed")
    where: dict[str, str] = {}
    for item in raw:
        entry = _record(item, _CONDITION_KEYS)
        name, value = entry.get("property"), entry.get("value")
        if not isinstance(name, str) or not isinstance(value, str) or not value.strip():
            raise CouldNotExpress("malformed")
        if name in where:  # one property twice is two conditions on one value: not equality
            raise CouldNotExpress("malformed")
        where[name] = value
    return where


def parse_proposal(
    data: dict[str, Any], vocabulary: Vocabulary, ontology: OntologySchema, placeholders: int
) -> tuple[PatternQuery, str]:
    """The model's answer as a validated `PatternQuery` and its explanation, or refused."""
    if data.get("can_express") is not True:
        raise CouldNotExpress("model_declined")
    raw_nodes, raw_edges = data.get("nodes"), data.get("edges", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise CouldNotExpress("malformed")
    if not raw_nodes:
        raise CouldNotExpress("no_pattern")

    nodes: list[PatternNode] = []
    for item in raw_nodes:
        entry = _record(item, _NODE_KEYS)
        var, entity_type = entry.get("var"), entry.get("entity_type")
        if not isinstance(var, str) or not _VARIABLE.match(var):
            raise CouldNotExpress("malformed")
        if any(n.var == var for n in nodes):
            raise CouldNotExpress("repeated_variable")
        if not isinstance(entity_type, str) or entity_type not in vocabulary.entity_types:
            raise CouldNotExpress("unknown_type")
        reference = entry.get("reference")
        if reference is not None:
            held = _PLACEHOLDER.match(reference) if isinstance(reference, str) else None
            if held is None or int(held.group(1)) > placeholders:
                raise CouldNotExpress("unresolved_reference")
        try:
            nodes.append(
                PatternNode(
                    var=var,
                    entity_type=entity_type,
                    node_id=reference,
                    where=_conditions(entry.get("where")),
                )
            )
        except ValidationError as error:
            raise CouldNotExpress("malformed") from error

    links = {link.name: link for link in vocabulary.links}
    kind = {n.var: n.entity_type or "" for n in nodes}
    edges: list[PatternEdge] = []
    for item in raw_edges:
        entry = _record(item, _EDGE_KEYS)
        name, source, target = entry.get("edge_type"), entry.get("from_var"), entry.get("to_var")
        if not isinstance(name, str) or name not in links:
            raise CouldNotExpress("unknown_link")
        if not isinstance(source, str) or not isinstance(target, str):
            raise CouldNotExpress("malformed")
        if source not in kind or target not in kind:
            raise CouldNotExpress("unknown_variable")
        if not links[name].joins(kind[source], kind[target]):
            raise CouldNotExpress("link_ends")
        edges.append(PatternEdge(edge_type=name, from_var=source, to_var=target))

    pattern = PatternQuery(nodes=nodes, edges=edges)
    try:
        check_pattern_conditions(pattern, ontology)
    except PatternConditionRefused as refused:
        raise CouldNotExpress("condition_refused", refused.detail) from refused
    return pattern, _one_line(data.get("explanation"), pattern)


class PatternProposer:
    """The model half, with no graph and no case: a question and the ontology in, a validated
    proposal out. The golden set calls this directly against a real model."""

    def __init__(self, model: ModelPort, *, default_model: str) -> None:
        self._model = model
        self._default_model = default_model

    async def propose(
        self,
        question: str,
        ontology: OntologySchema,
        *,
        placeholders: int = 0,
        document_id: str = "ask-to-search",
    ) -> Proposal:
        vocabulary = vocabulary_of(ontology)
        # Handling is not given: the text holds the ontology and the analyst's own words, no
        # record, and a client's provider is never sent material with no handling
        # (`model_routing.py`).
        result = await self._model.extract(
            ExtractionRequest(
                document_id=document_id,
                text=(
                    f"{_INSTRUCTIONS}\n\n{vocabulary.text()}\n\n"
                    f"{_selection_instruction(placeholders)}\n\nQuestion: {question}"
                ),
                json_schema=proposal_schema(vocabulary, placeholders),
                model=self._default_model,
                handling=None,
            )
        )
        pattern, explanation = parse_proposal(result.data, vocabulary, ontology, placeholders)
        return Proposal(pattern=pattern, explanation=explanation, model=result.model)


def resolve_references(pattern: PatternQuery, selection: Sequence[str]) -> PatternQuery:
    """The pattern with each `$selected_n` replaced by the nth id of `selection`. A placeholder past
    the selection is refused: the proposal was validated for exactly this many."""
    nodes: list[PatternNode] = []
    for node in pattern.nodes:
        held = _PLACEHOLDER.match(node.node_id) if node.node_id else None
        if held is None:
            nodes.append(node)
            continue
        position = int(held.group(1))
        if position > len(selection):
            raise CouldNotExpress("unresolved_reference")
        nodes.append(node.model_copy(update={"node_id": selection[position - 1]}))
    return pattern.model_copy(update={"nodes": nodes})


class PatternAskService:
    def __init__(
        self,
        working_set: WorkingSetService,
        graph: GraphPort,
        model: ModelPort,
        *,
        default_model: str,
    ) -> None:
        self._working_set = working_set
        self._graph = graph
        self._proposer = PatternProposer(model, default_model=default_model)

    async def _selection_the_analyst_may_use(
        self, investigation_id: str, selected: Sequence[str], principal: Principal
    ) -> list[str]:
        """The selected ids in this case's view as `principal` may see it, in the order sent and
        without repeats. An id they may not see and an id that does not exist are both left out,
        so nothing downstream, the numbering and the prompt included, can tell them apart."""
        if not selected:
            return []
        visible, _ = await self._working_set.visible_membership(investigation_id, principal)
        seen = {n.id for n in visible}
        usable: list[str] = []
        for node_id in selected:
            if node_id in seen and node_id not in usable:
                usable.append(node_id)
        return usable

    async def ask(
        self,
        investigation_id: str,
        request: AskToSearchRequest,
        principal: Principal,
        ontology: OntologySchema,
    ) -> PatternProposal:
        selection = await self._selection_the_analyst_may_use(
            investigation_id, request.selected_node_ids, principal
        )
        proposal = await self._proposer.propose(
            request.question,
            ontology,
            placeholders=len(selection),
            document_id=f"ask-to-search:{investigation_id}",
        )
        pattern = resolve_references(proposal.pattern, selection)
        try:
            # The preview route's own function: the count is the store's, as the reader, and
            # nothing is matched, queued or stored.
            preview = await preview_pattern(pattern, graph=self._graph, principal=principal)
        except ValueError as error:
            raise CouldNotExpress("not_runnable") from error
        return PatternProposal(
            pattern=pattern,
            explanation=proposal.explanation,
            estimated_count=preview.estimated_count,
            is_floor=preview.is_floor,
        )


__all__: Sequence[str] = (
    "AskToSearchRequest",
    "CouldNotExpress",
    "CouldNotExpressBody",
    "PatternAskService",
    "PatternProposal",
    "PatternProposer",
    "Proposal",
    "Vocabulary",
    "describe_pattern",
    "parse_proposal",
    "proposal_schema",
    "resolve_references",
    "vocabulary_of",
)
