"""Rules written as sentences (`06_DECISIONS.md` ADR-133 decisions 1 and 3, stage (b)).

**A sentence is checked against the ontology, never parsed (rule 8).** `RuleSentence`
(`packages/schemas/sentences.py`) is a set of closed choices; `check_sentence` refuses, by the blank
it is about and in words, any type, property or link type the deployment's ontology does not
declare, and any choice that does not fit what it names (an "above" on a text property, a link
that does not reach the subject's type, an amount that is not a number).

**It compiles to what exists** (`compile_sentence`): a drawn pattern (ADR-109 phase D) — the
subject as the variable `subject`, the equality conditions a pattern may carry (ADR-121: indexed
text, not `sensitivity: high`, at most three) and the link the sentence names — plus the sentence
itself as the rule's typed parameters (`SentenceRuleParams`). **The drawn pattern is the
sentence's "advanced" view, and the two are one rule:** `sentence_of` reads a pattern drawn or
edited in the query builder back as the sentence, keeping the sentence's other blanks, and a
sentence and its drawn pattern compile to the same rule (`test_rule_sentences.py`).

**Evaluated as its author, in the stores (rule 3).** `judge_sentence` (as data loads) and
`preview_sentence` (decision 3) share one judgement: subjects read through `GraphPort` as the
author (a pinned match for a link; `expand` for "within N steps"), each further condition on what
the author read, a hotlist from the author's own, and a frequency or amount through
`AnalyticsPort.event_frequency` as the author, the access step in its query. Nothing is counted
over anything the author could not have read, so a preview's count and examples say nothing of a
hidden node (rule 7).

**Never in part (rule 2).** A load that would judge more than the rule's `max_matches` subjects is
refused in words; a preview whose subjects would pass the working-set limit is refused with the
typed `limit_exceeded`, counted as the author, never counted in part.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from ontology.handling import HandlingScheme
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.analytics import EventFilter, EventRecord, FrequencyRequest, NodeFrequency
from schemas.domain import (
    CompiledSentence,
    EdgeTypeDef,
    EdgeWrite,
    EntityTypeDef,
    ExpandRequest,
    Interval,
    Node,
    NodeWrite,
    OntologySchema,
    PatternEdge,
    PatternNode,
    PatternQuery,
    Principal,
    PropertyType,
    TypologyRule,
)
from schemas.sentences import (
    PREVIEW_DAYS,
    PREVIEW_EXAMPLES,
    AreaPoint,
    DrawnArea,
    EqualsCondition,
    LinkedRelationship,
    PreviewExample,
    RulePreview,
    RuleSentence,
    SentenceCondition,
    SentenceRefusal,
    SentenceRuleParams,
)
from schemas.strength import ActiveInfluencer, RarityMeasure, StrengthComposition

from .alert_queue import node_name
from .working_set.models import MAX_NODES, LimitExceeded, LimitExceededError

#: The variable a compiled sentence's subject takes in its drawn pattern.
SUBJECT_VAR = "subject"
OTHER_VAR = "other"
#: ADR-121's own bound on a pattern node's conditions.
_PATTERN_WHERE_MAX = 3

_TEXT = frozenset({PropertyType.STRING, PropertyType.ENUM})
_NUMBERS = frozenset({PropertyType.INTEGER, PropertyType.FLOAT})
_TIMES = frozenset({PropertyType.DATE, PropertyType.DATETIME})
_EQUALS_TYPES = _TEXT | _NUMBERS | _TIMES | {PropertyType.BOOLEAN}
_SCREENED_TYPES = frozenset({"Person", "Organisation"})

Reason = Literal[
    "unknown_type",
    "unknown_property",
    "sensitive",
    "unsupported_type",
    "unknown_value",
    "not_a_place",
    "unknown_link_type",
    "link_not_for_subject",
    "link_not_for_other",
    "no_identifier",
    "not_screened",
    "not_events",
    "not_a_sentence",
]


class SentenceRefused(Exception):
    """A sentence the ontology refuses — by blank, reason and words (a typed 422 at the route)."""

    def __init__(self, blank: str, reason: Reason, detail: str) -> None:
        super().__init__(detail)
        self.refusal = SentenceRefusal(blank=blank, reason=reason, detail=detail)


# --- checking against the ontology --------------------------------------------------------------


def _link_label(edge: EdgeTypeDef) -> str:
    return edge.label or edge.name.replace("_", " ").capitalize()


def _reaches(types: Sequence[str], entity_type: str) -> bool:
    return "*" in types or entity_type in types


def _entity(ontology: OntologySchema, name: str, blank: str) -> EntityTypeDef:
    found = ontology.entity_type(name)
    if found is None:
        raise SentenceRefused(blank, "unknown_type", f"{name!r} is not a type in the ontology")
    return found


def _link(ontology: OntologySchema, name: str, blank: str) -> EdgeTypeDef:
    found = ontology.edge_type(name)
    if found is None or found.system or found.hidden:
        raise SentenceRefused(
            blank, "unknown_link_type", f"{name!r} is not a link type the ontology declares"
        )
    return found


def _touches(edge: EdgeTypeDef, entity_type: str) -> bool:
    return _reaches(edge.from_types, entity_type) or _reaches(edge.to_types, entity_type)


def _check_condition(subject: EntityTypeDef, condition: SentenceCondition, at: int) -> None:
    blank = f"conditions[{at}]"
    declared = next((p for p in subject.properties if p.name == condition.property), None)
    if declared is None:
        raise SentenceRefused(
            blank,
            "unknown_property",
            f"{subject.name!r} declares no property {condition.property!r}",
        )
    if declared.sensitivity == "high":
        raise SentenceRefused(
            blank,
            "sensitive",
            f"{subject.name}.{declared.name} is marked sensitivity: high, so a rule cannot test it",
        )
    fits: dict[str, frozenset[PropertyType]] = {
        "equals": _EQUALS_TYPES,
        "one_of": _TEXT,
        "above": _NUMBERS,
        "below": _NUMBERS,
        "within_time": _TIMES,
        "within_area": frozenset({PropertyType.STRING}),
    }
    if declared.type not in fits[condition.op]:
        raise SentenceRefused(
            blank,
            "unsupported_type",
            f"{subject.name}.{declared.name} is of type {declared.type.value!r}, "
            f"which “{condition.op.replace('_', ' ')}” does not fit",
        )
    if condition.op == "within_area" and declared.name != "geometry_ref":
        raise SentenceRefused(
            blank, "not_a_place", f"{subject.name}.{declared.name} does not name a place"
        )
    if declared.type is PropertyType.ENUM and declared.values:
        given = [condition.value] if condition.op == "equals" else getattr(condition, "values", [])
        unknown = [v for v in given if v not in declared.values]
        if unknown:
            raise SentenceRefused(
                blank,
                "unknown_value",
                f"{subject.name}.{declared.name} is one of {', '.join(declared.values)}; "
                f"{unknown[0]!r} is not",
            )
    if (
        declared.type is PropertyType.BOOLEAN
        and condition.op == "equals"
        and condition.value not in ("true", "false")
    ):
        raise SentenceRefused(blank, "unknown_value", f"{declared.name} is yes or no")


def check_sentence(sentence: RuleSentence, ontology: OntologySchema) -> None:
    """Raises `SentenceRefused` for the first blank the ontology refuses; returns when every name
    in the sentence is one the ontology declares and every choice fits what it names."""
    subject = _entity(ontology, sentence.subject, "subject")
    for at, condition in enumerate(sentence.conditions):
        _check_condition(subject, condition, at)
    relationship = sentence.relationship
    if relationship is not None:
        blank = "relationship"
        if relationship.kind == "linked":
            edge = _link(ontology, relationship.link_type, blank)
            if not _touches(edge, subject.name):
                raise SentenceRefused(
                    blank,
                    "link_not_for_subject",
                    f"“{_link_label(edge)}” does not link a {subject.name}",
                )
            if relationship.other_type is not None:
                other = _entity(ontology, relationship.other_type, blank)
                ends = edge.to_types if _reaches(edge.from_types, subject.name) else edge.from_types
                if not _reaches(ends, other.name) and not _touches(edge, other.name):
                    raise SentenceRefused(
                        blank,
                        "link_not_for_other",
                        f"“{_link_label(edge)}” does not link a {subject.name} to a {other.name}",
                    )
        elif relationship.kind == "within_steps":
            _entity(ontology, relationship.other_type, blank)
        elif relationship.kind == "at_location":
            edge = _link(ontology, relationship.link_type, blank)
            if not _touches(edge, subject.name) or not _touches(edge, "Location"):
                raise SentenceRefused(
                    blank,
                    "link_not_for_subject",
                    f"“{_link_label(edge)}” does not link a {subject.name} to a Location",
                )
        elif relationship.kind == "on_hotlist":
            named = "value_normalised" in {p.name for p in subject.properties}
            if not subject.identifiers and not named:
                raise SentenceRefused(
                    blank, "no_identifier", f"a {subject.name} carries no identifier to hotlist"
                )
        elif subject.name not in _SCREENED_TYPES:
            raise SentenceRefused(
                blank, "not_screened", "only a Person or an Organisation is screened by name"
            )
    strength = sentence.strength
    if strength is not None and strength.kind == "connection_strength":
        if strength.link_type is not None:
            edge = _link(ontology, strength.link_type, "strength")
            if not _touches(edge, subject.name):
                raise SentenceRefused(
                    "strength",
                    "link_not_for_subject",
                    f"“{_link_label(edge)}” does not link a {subject.name}",
                )
        if strength.other_type is not None:
            _entity(ontology, strength.other_type, "strength")
    frequency = sentence.frequency
    if frequency is not None:
        edge = _link(ontology, frequency.link_type, "frequency")
        if not _touches(edge, subject.name):
            raise SentenceRefused(
                "frequency",
                "link_not_for_subject",
                f"“{_link_label(edge)}” does not link a {subject.name}",
            )
        if not edge.temporal:
            raise SentenceRefused(
                "frequency",
                "not_events",
                f"“{_link_label(edge)}” carries no dated events to count",
            )
        if frequency.kind == "amount":
            amount = next((p for p in edge.properties if p.name == frequency.amount_property), None)
            if amount is None or amount.type not in _NUMBERS:
                raise SentenceRefused(
                    "frequency",
                    "unknown_property",
                    f"“{_link_label(edge)}” declares no amount {frequency.amount_property!r}",
                )


# --- compiling to a drawn pattern, and reading one back ----------------------------------------


def _pattern_eligible(subject: EntityTypeDef, condition: SentenceCondition) -> bool:
    """ADR-121: what a pattern node may carry — equality on indexed text, not sensitive."""
    if not isinstance(condition, EqualsCondition):
        return False
    declared = next((p for p in subject.properties if p.name == condition.property), None)
    return (
        declared is not None
        and declared.indexed
        and declared.type in _TEXT
        and declared.sensitivity != "high"
    )


def _split(
    sentence: RuleSentence, ontology: OntologySchema
) -> tuple[dict[str, str], list[SentenceCondition]]:
    """The conditions the drawn pattern carries (the first three eligible, by property name) and
    the rest, which the rule's parameters carry."""
    subject = _entity(ontology, sentence.subject, "subject")
    where: dict[str, str] = {}
    rest: list[SentenceCondition] = []
    for condition in sorted(sentence.conditions, key=lambda c: c.property):
        if _pattern_eligible(subject, condition) and len(where) < _PATTERN_WHERE_MAX:
            assert isinstance(condition, EqualsCondition)
            where[condition.property] = condition.value
        else:
            rest.append(condition)
    return where, rest


def normalised(sentence: RuleSentence) -> RuleSentence:
    """Conditions in property order: the order a sentence lists them in is not part of the rule."""
    return sentence.model_copy(
        update={"conditions": sorted(sentence.conditions, key=lambda c: c.property)}
    )


def compile_pattern(sentence: RuleSentence, ontology: OntologySchema) -> PatternQuery:
    check_sentence(sentence, ontology)
    where, _ = _split(sentence, ontology)
    nodes = [PatternNode(var=SUBJECT_VAR, entity_type=sentence.subject, where=where)]
    edges: list[PatternEdge] = []
    relationship = sentence.relationship
    if isinstance(relationship, LinkedRelationship):
        edge = _link(ontology, relationship.link_type, "relationship")
        nodes.append(PatternNode(var=OTHER_VAR, entity_type=relationship.other_type))
        outward = _reaches(edge.from_types, sentence.subject)
        edges.append(
            PatternEdge(
                edge_type=edge.name,
                from_var=SUBJECT_VAR if outward else OTHER_VAR,
                to_var=OTHER_VAR if outward else SUBJECT_VAR,
            )
        )
    return PatternQuery(nodes=nodes, edges=edges, limit=MAX_NODES)


def compile_sentence(sentence: RuleSentence, ontology: OntologySchema) -> CompiledSentence:
    return CompiledSentence(
        pattern=compile_pattern(sentence, ontology),
        words=sentence_words(normalised(sentence), ontology),
    )


def _subject_node(pattern: PatternQuery, subject_type: str | None = None) -> PatternNode:
    """The subject: the variable `subject` as compiled; in a pattern drawn by hand, the one node of
    the sentence's subject type, else the first drawn."""
    named = [n for n in pattern.nodes if n.var == SUBJECT_VAR]
    if named:
        return named[0]
    typed = [n for n in pattern.nodes if n.entity_type == subject_type]
    return typed[0] if len(typed) == 1 else pattern.nodes[0]


def sentence_of(
    pattern: PatternQuery, sentence: RuleSentence, ontology: OntologySchema
) -> RuleSentence:
    """A drawn pattern read back as a sentence, keeping `sentence`'s other blanks: the subject, its
    equality conditions and the link come from the pattern; everything a pattern cannot say comes
    from `sentence`. A pattern a sentence cannot say — more than one link, a pinned node, an
    untyped subject — is refused in words, to be kept as a drawn pattern rule instead."""

    def refuse(detail: str) -> SentenceRefused:
        return SentenceRefused("pattern", "not_a_sentence", detail)

    if not pattern.nodes or len(pattern.nodes) > 2 or len(pattern.edges) != len(pattern.nodes) - 1:
        raise refuse("a sentence says one subject and at most one link to one other thing")
    if any(n.node_id for n in pattern.nodes):
        raise refuse("a sentence speaks of every node of a type, not one pinned node")
    subject = _subject_node(pattern, sentence.subject)
    if not subject.entity_type:
        raise refuse("the subject of a sentence has a type")
    other = next((n for n in pattern.nodes if n is not subject), None)
    if other is not None and other.where:
        raise refuse("a sentence tests its subject's properties, not the other end's")
    base = sentence.model_copy(update={"subject": subject.entity_type, "conditions": []})
    _, rest = _split(sentence, ontology) if sentence.subject == subject.entity_type else ({}, [])
    conditions: list[SentenceCondition] = [
        EqualsCondition(property=k, value=v) for k, v in subject.where.items()
    ]
    conditions.extend(c for c in rest if c.property not in subject.where)
    relationship = sentence.relationship
    if pattern.edges:
        relationship = LinkedRelationship(
            link_type=pattern.edges[0].edge_type,
            other_type=other.entity_type if other is not None else None,
        )
    elif isinstance(relationship, LinkedRelationship):
        relationship = None
    read = normalised(
        RuleSentence.model_validate(
            {
                **base.model_dump(),
                "conditions": [c.model_dump() for c in conditions],
                "relationship": relationship.model_dump() if relationship else None,
            }
        )
    )
    check_sentence(read, ontology)
    return read


# --- the sentence in words ------------------------------------------------------------------------


def _a(noun: str) -> str:
    return f"{'an' if noun[:1].lower() in 'aeiou' else 'a'} {noun}"


def _number(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,}"


def _condition_words(condition: SentenceCondition) -> str:
    name = condition.property.replace("_", " ")
    match condition.op:
        case "equals":
            return f"{name} is {condition.value}"
        case "one_of":
            return f"{name} is one of {', '.join(condition.values)}"
        case "above":
            return f"{name} is above {_number(condition.value)}"
        case "below":
            return f"{name} is below {_number(condition.value)}"
        case "within_area":
            return f"place is within {condition.area.name}"
        case _:
            start = condition.start.date().isoformat() if condition.start else None
            end = condition.end.date().isoformat() if condition.end else None
            if start and end:
                return f"{name} is between {start} and {end}"
            return f"{name} is from {start}" if start else f"{name} is up to {end}"


def sentence_words(sentence: RuleSentence, ontology: OntologySchema | None = None) -> str:
    """The rule as one sentence, the words the builder shows and every alert it raises carries."""

    def label(link_type: str) -> str:
        edge = ontology.edge_type(link_type) if ontology is not None else None
        return _link_label(edge) if edge is not None else link_type

    opening = f"When {_a(sentence.subject)}"
    if sentence.conditions:
        opening += " whose " + " and ".join(_condition_words(c) for c in sentence.conditions)
    words = [opening]
    relationship = sentence.relationship
    if relationship is not None:
        match relationship.kind:
            case "linked":
                words.append(
                    f"is linked by “{label(relationship.link_type)}” to "
                    + (_a(relationship.other_type) if relationship.other_type else "anything")
                )
            case "within_steps":
                words.append(
                    f"is within {relationship.steps} step(s) of {_a(relationship.other_type)}"
                )
            case "at_location":
                words.append(
                    f"is at a location within {relationship.area.name} "
                    f"(by “{label(relationship.link_type)}”)"
                )
            case "on_hotlist":
                words.append("is on one of my hotlists")
            case _:
                words.append(f"is on a screening list (name match {relationship.min_score:g})")
    frequency = sentence.frequency
    if frequency is not None:
        link = label(frequency.link_type)
        match frequency.kind:
            case "count":
                words.append(
                    f"{frequency.at_least} or more times by “{link}” "
                    f"within {frequency.within_days} day(s)"
                )
            case "amount":
                words.append(
                    f"with a total {frequency.amount_property.replace('_', ' ')} over "
                    f"{_number(frequency.over)} by “{link}” within {frequency.within_days} day(s)"
                )
            case _:
                words.append(f"for the first time ever by “{link}”")
    strength = sentence.strength
    if strength is not None:
        if strength.kind == "connection_strength":
            other = _a(strength.other_type) if strength.other_type else "anything it is linked to"
            by = f" by “{label(strength.link_type)}”" if strength.link_type else ""
            scale = " on the client's scale" if strength.scale == "client" else ""
            words.append(
                f"and the connection strength between it and {other}{by} reaches "
                f"{_number(strength.reaches)}{scale}"
            )
        else:
            where = "per dataset" if strength.scope == "dataset" else "across the case's datasets"
            words.append(
                f"and the shared-attribute rarity between it and another {sentence.subject} "
                f"reaches {_number(strength.reaches)} ({where})"
            )
    team = "my team" if sentence.team == "my_team" else "the case team"
    audience = {"just_me": "me alone", "this_case": team, "deployment": "every case's team"}
    if sentence.runs == "schedule" and sentence.schedule is not None:
        from .rule_schedule import schedule_words

        runs = f"on a schedule, {schedule_words(sentence.schedule)}"
    else:
        runs = (
            "before each load commits"
            if sentence.runs == "pre_commit"
            else "after each load commits"
        )
    hold = ", holding its rows for review" if sentence.on_hit == "hold" else ""
    return (
        ", ".join(words)
        + f", raise a {sentence.severity}-severity alert for {audience[sentence.scope]}, "
        + f"{runs}{hold}."
    )


# --- judging subjects (shared by evaluation and preview) ---------------------------------------


@dataclass
class SentenceContext:
    """What judging a sentence reads, each as the rule's author."""

    graph: GraphPort
    analytics: AnalyticsPort | None
    investigation_scope: str
    ontology: OntologySchema | None = None
    #: The author's own hotlists' identifiers (ADR-038), read as them; `None` when not read.
    hotlisted: frozenset[str] | None = None
    #: Screening-list entries by entity type, reference data (ADR-109 phase F).
    screening_entries: dict[str, list[Any]] = field(default_factory=dict)
    #: ADR-139: the link-strength influencers in force in the case (case, then installation, then
    #: the weights file's), which a strength condition judges by; and the types rarity leaves out.
    influencers: Sequence[ActiveInfluencer] = ()
    rarity_exclude_types: tuple[str, ...] = ("Alert",)
    #: ADR-139 Amendment 2: the composition and rarity measure in force in the case.
    composition: StrengthComposition = "standard"
    rarity_measure: RarityMeasure = "share"


@dataclass(frozen=True)
class Hit:
    node: Node
    words: str
    refs: tuple[str, ...]


def _inside(area: DrawnArea, lon: float, lat: float) -> bool:
    """A point within a closed outline, by crossings (a point on an edge counts as inside)."""
    points: list[AreaPoint] = area.points
    inside = False
    j = len(points) - 1
    for i, p in enumerate(points):
        q = points[j]
        if (p.lat > lat) != (q.lat > lat):
            crossing = (q.lon - p.lon) * (lat - p.lat) / (q.lat - p.lat) + p.lon
            if lon == crossing:
                return True
            if lon < crossing:
                inside = not inside
        j = i
    return inside


def _as_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


async def _places(
    refs: Sequence[str], author: Principal, ctx: SentenceContext
) -> dict[str, tuple[float, float]]:
    """Each geometry the author may read, as its point: a place without one point is in no area."""
    if not refs or ctx.analytics is None:
        return {}
    found = await ctx.analytics.get_geometries(sorted(set(refs)), author)
    return {
        g.geometry_ref: (g.lon, g.lat) for g in found if g.lon is not None and g.lat is not None
    }


async def _meets_conditions(
    node: Node, conditions: Sequence[SentenceCondition], author: Principal, ctx: SentenceContext
) -> bool:
    for condition in conditions:
        value = node.properties.get(condition.property)
        if value is None:
            return False
        match condition.op:
            case "equals":
                if _text(value) != condition.value:
                    return False
            case "one_of":
                if _text(value) not in condition.values:
                    return False
            case "above" | "below":
                number = _as_number(value)
                if number is None:
                    return False
                if condition.op == "above" and not number > condition.value:
                    return False
                if condition.op == "below" and not number < condition.value:
                    return False
            case "within_time":
                at = _as_time(value)
                if at is None:
                    return False
                if condition.start is not None and at < _as_time(condition.start):  # type: ignore[operator]
                    return False
                if condition.end is not None and at > _as_time(condition.end):  # type: ignore[operator]
                    return False
            case "within_area":
                point = (await _places([str(value)], author, ctx)).get(str(value))
                if point is None or not _inside(condition.area, *point):
                    return False
    return True


def _identifiers(node: Node, ontology: OntologySchema | None) -> set[str]:
    """What a hotlist identifier is matched against on the subject: what the hotlist evaluation
    watches (`evaluation.watched_values`: `value_normalised`, and an account's number, ADR-108
    Amendment 5), and any property named as one of the type's declared identifiers."""
    from .evaluation import watched_values

    names = {"value_normalised"}
    if ontology is not None:
        declared = ontology.entity_type(node.type)
        if declared is not None:
            names.update(declared.identifiers)
    found = {str(node.properties[n]) for n in names if node.properties.get(n)}
    return found | watched_values(node.properties)


def _screening_name(node: Node) -> str:
    if node.type == "Person":
        return " ".join(
            str(node.properties.get(k) or "") for k in ("given_names", "family_name")
        ).strip()
    return str(node.properties.get("name") or "")


async def _meets_relationship(
    node: Node, sentence: RuleSentence, author: Principal, ctx: SentenceContext
) -> str | None:
    """`None` when the subject fails the relationship; else the words it adds (may be empty)."""
    relationship = sentence.relationship
    if relationship is None or relationship.kind == "linked":
        return ""  # a link is the drawn pattern's, matched pinned to the subject as the author
    if relationship.kind == "within_steps":
        reached = await ctx.graph.expand(
            ExpandRequest(node_ids=[node.id], depth=relationship.steps), author
        )
        near = [n for n in reached.nodes if n.id != node.id and n.type == relationship.other_type]
        return f"within {relationship.steps} step(s) of {node_name(near[0])}" if near else None
    if relationship.kind == "at_location":
        reached = await ctx.graph.expand(
            ExpandRequest(node_ids=[node.id], depth=1, edge_types=[relationship.link_type]),
            author,
        )
        locations = [n for n in reached.nodes if n.type == "Location" and n.id != node.id]
        refs = [str(n.properties["geometry_ref"]) for n in locations
                if n.properties.get("geometry_ref")]  # fmt: skip
        places = await _places(refs, author, ctx)
        for location in locations:
            point = places.get(str(location.properties.get("geometry_ref")))
            if point is not None and _inside(relationship.area, *point):
                return f"at {node_name(location)}, within {relationship.area.name}"
        return None
    if relationship.kind == "on_hotlist":
        hotlisted = ctx.hotlisted or frozenset()
        listed = _identifiers(node, ctx.ontology) & hotlisted
        return "on one of the author's hotlists" if listed else None
    from .screening import screen

    entries = ctx.screening_entries.get(node.type, [])
    hits = screen(_screening_name(node), None, entries, min_score=relationship.min_score)
    if not hits:
        return None
    return f"a {hits[0].score:.2f} match to an entry on {hits[0].entry.list_name}"


async def _meets_strength(
    node: Node, sentence: RuleSentence, author: Principal, ctx: SentenceContext
) -> str | None:
    """ADR-139 decision 8: `None` when the subject's strength (or rarity) does not reach the
    sentence's figure, as the author may see it; else the words it adds. Both are worked out in
    the graph adapter under the author's access, so evidence the author could not read never
    raises an alert."""
    strength = sentence.strength
    if strength is None:
        return ""
    if strength.kind == "connection_strength":
        reached = await ctx.graph.expand(
            ExpandRequest(
                node_ids=[node.id], depth=1,
                edge_types=[strength.link_type] if strength.link_type else [],
            ),
            author,
        )  # fmt: skip
        others = {n.id: n for n in reached.nodes}
        ends: dict[str, str] = {}
        for edge in reached.edges:
            if node.id not in (edge.source, edge.target):
                continue
            other_id = edge.target if edge.source == node.id else edge.source
            other = others.get(other_id)
            if other is None or (strength.other_type and other.type != strength.other_type):
                continue
            ends[edge.id] = other_id
        if not ends:
            return None
        found = await ctx.graph.connection_strengths(
            sorted(ends), author, influencers=ctx.influencers, composition=ctx.composition
        )
        if strength.scale == "client":
            # The client's raw sum exists only under client parity (Amendment 2).
            sums = [s for s in found if s.raw_sum is not None]
            best = max(sums, key=lambda s: (s.raw_sum or 0.0, s.edge_id), default=None)
            if best is None or (best.raw_sum or 0.0) < strength.reaches:
                return None
            return (
                f"connection strength {best.raw_sum:.2f} on the client's scale with "
                f"{node_name(others[ends[best.edge_id]])}"
            )
        best = max(found, key=lambda s: (s.strength, s.edge_id), default=None)
        if best is None or best.strength < strength.reaches:
            return None
        return (
            f"connection strength {best.strength:.2f} with {node_name(others[ends[best.edge_id]])}"
        )
    result = await ctx.graph.shared_attribute_rarity(
        [node.id], author, scope=strength.scope, partners="any",
        exclude_types=ctx.rarity_exclude_types, measure=ctx.rarity_measure,
    )  # fmt: skip
    value = result.node_values.get(node.id)
    if value is None or value < strength.reaches:
        return None
    partner = next((p.b for p in result.pairs if p.a == node.id), None)
    named = await ctx.graph.get_nodes([partner], author) if partner else []
    with_whom = f" with {node_name(named[0])}" if named else ""
    return f"shared-attribute rarity {value:.2f}{with_whom}"


async def _frequencies(
    subjects: Sequence[Node],
    sentence: RuleSentence,
    author: Principal,
    ctx: SentenceContext,
    window: Interval,
) -> dict[str, NodeFrequency]:
    frequency = sentence.frequency
    if frequency is None or not subjects:
        return {}
    if ctx.analytics is None:
        raise RuntimeError("this run has no analytics store to count the subjects' events in")
    span = getattr(frequency, "within_days", 1)
    amount = frequency.amount_property if frequency.kind == "amount" else None
    result = await ctx.analytics.event_frequency(
        FrequencyRequest(
            filter=EventFilter(
                investigation_scope=ctx.investigation_scope,
                window=window,
                node_ids=sorted({n.id for n in subjects}),
                edge_types=[frequency.link_type],
            ),
            span_days=span,
            amount_property=amount,
        ),
        author,
    )
    return result.nodes


def _meets_frequency(
    sentence: RuleSentence, counted: NodeFrequency | None, firsts: Interval
) -> str | None:
    frequency = sentence.frequency
    if frequency is None:
        return ""
    if counted is None:
        return None
    if frequency.kind == "count":
        if counted.most_in_span < frequency.at_least:
            return None
        return f"{counted.most_in_span} times within {frequency.within_days} day(s)"
    if frequency.kind == "amount":
        if counted.largest_total is None or not counted.largest_total > frequency.over:
            return None
        return f"a total of {_number(counted.largest_total)} within {frequency.within_days} day(s)"
    first = counted.first_at
    if first is None or first < firsts.valid_from:
        return None
    if firsts.valid_to is not None and first > firsts.valid_to:
        return None
    return f"for the first time on {first.date().isoformat()}"


async def judge_subjects(
    subjects: Sequence[Node],
    sentence: RuleSentence,
    author: Principal,
    ctx: SentenceContext,
    *,
    window: Interval,
    firsts: Interval,
    conditions: Sequence[SentenceCondition] | None = None,
) -> list[Hit]:
    """Each subject that meets the sentence's further conditions, relationship and frequency — read
    as `author`. `conditions` are those still to test (all of them by default)."""
    kept: list[tuple[Node, list[str]]] = []
    tested = sentence.conditions if conditions is None else conditions
    for node in subjects:
        if not await _meets_conditions(node, tested, author, ctx):
            continue
        said = await _meets_relationship(node, sentence, author, ctx)
        if said is None:
            continue
        strong = await _meets_strength(node, sentence, author, ctx)
        if strong is None:
            continue
        kept.append((node, [w for w in (said, strong) if w]))
    counts = await _frequencies([n for n, _ in kept], sentence, author, ctx, window)
    hits: list[Hit] = []
    for node, reasons in kept:
        often = _meets_frequency(sentence, counts.get(node.id), firsts)
        if often is None:
            continue
        detail = "; ".join(s for s in [*reasons, often] if s)
        words = f"{node_name(node)} ({node.type})" + (f": {detail}" if detail else "")
        stamp = (
            counts[node.id].first_at.isoformat()  # type: ignore[union-attr]
            if sentence.frequency is not None and counts.get(node.id) and counts[node.id].first_at
            else ""
        )
        hits.append(Hit(node=node, words=words, refs=(node.id, often or "", stamp)))
    return hits


def _pinned(pattern: PatternQuery, node_id: str, subject_type: str) -> PatternQuery:
    subject = _subject_node(pattern, subject_type)
    pinned = subject.model_copy(update={"node_id": node_id})
    ordered = [pinned, *(n for n in pattern.nodes if n is not subject)]
    return pattern.model_copy(update={"nodes": ordered, "limit": 1})


def _where_holds(node: Node, where: dict[str, str]) -> bool:
    return all(_text(node.properties.get(k)) == v for k, v in where.items())


# --- as data loads (ADR-109's chassis) ----------------------------------------------------------


def _subject_ids(
    sentence: RuleSentence,
    written: Sequence[NodeWrite | EdgeWrite],
    events: Sequence[EventRecord],
) -> set[str]:
    """What this load touched that may be a subject: what it wrote of the subject's type, and both
    ends of each link and event it wrote (a frequency rule's subject may only gain an event)."""
    ids = {w.id for w in written if isinstance(w, NodeWrite) and w.type == sentence.subject}
    for write in written:
        if isinstance(write, EdgeWrite):
            ids.update({write.source, write.target})
    for event in events:
        ids.update({event.source_id, event.target_id})
    return ids


async def judge_sentence(
    rule: TypologyRule,
    author: Principal,
    written: Sequence[NodeWrite | EdgeWrite],
    events: Sequence[EventRecord],
    ctx: SentenceContext,
    *,
    pattern: PatternQuery,
    scheme: HandlingScheme,
    now: datetime | None = None,
) -> list[Hit]:
    """The sentence over one load, as its author. `pattern` is its drawn pattern, read afresh as the
    author by the caller. Before commit, what the load wrote is judged as written (readable to the
    author by its marking); after it, as the store holds it."""
    params = rule.params
    assert isinstance(params, SentenceRuleParams)
    sentence = params.sentence
    if ctx.ontology is not None:
        sentence = sentence_of(pattern, sentence, ctx.ontology)
    subject_pattern = _subject_node(pattern, sentence.subject)
    candidate_ids = sorted(_subject_ids(sentence, written, events))
    from .rule_evaluation import handling_readable

    pending = {
        w.id: w
        for w in written
        if isinstance(w, NodeWrite)
        and w.type == sentence.subject
        and handling_readable(scheme, author, w.handling)
    }
    stored = [i for i in candidate_ids if i not in pending]
    read = await ctx.graph.get_nodes(stored, author) if stored else []
    nodes = [n for n in read if n.type == sentence.subject]
    if rule.trigger == "pre_commit":
        nodes.extend(_as_node(w) for w in pending.values())
    elif pending:
        nodes.extend(
            n for n in await ctx.graph.get_nodes(sorted(pending), author)
            if n.type == sentence.subject
        )  # fmt: skip
    subjects = {n.id: n for n in nodes}
    if len(subjects) > params.max_matches:
        raise RuntimeError(
            f"this load touched {len(subjects):,} subjects, more than the rule's "
            f"{params.max_matches:,}; not judged on part of them"
        )
    passing = [n for n in subjects.values() if _where_holds(n, subject_pattern.where)]
    if pattern.edges:
        linked = []
        for node in passing:
            pinned = _pinned(pattern, node.id, sentence.subject)
            if await ctx.graph.match_count(pinned, author, ceiling=1) > 0:
                linked.append(node)
        passing = linked
    times = [e.occurred_at for e in events]
    stamp = now or datetime.now(UTC)
    span = timedelta(days=getattr(sentence.frequency, "within_days", 0))
    end = max(times) if times else stamp
    start = min(times) if times else stamp
    rest = (
        _split(sentence, ctx.ontology)[1] if ctx.ontology is not None else list(sentence.conditions)
    )
    return await judge_subjects(
        passing,
        sentence,
        author,
        ctx,
        window=Interval(valid_from=start - span, valid_to=end),
        firsts=Interval(valid_from=start, valid_to=end),
        conditions=rest,
    )


def _as_node(write: NodeWrite) -> Node:
    from schemas.domain import AuditStub

    return Node(
        id=write.id,
        type=write.type,
        properties=write.properties,
        provenance=write.provenance,
        handling=write.handling,
        audit=AuditStub(created_at=write.created_at, created_by=write.created_by, revision=0),
        datasets=write.datasets,
    )


def hit_signature(rule_id: str, hit: Hit) -> str:
    return hashlib.sha256("|".join([rule_id, "sentence", *hit.refs]).encode()).hexdigest()


# --- the preview (decision 3) -------------------------------------------------------------------


async def preview_sentence(
    sentence: RuleSentence,
    author: Principal,
    ctx: SentenceContext,
    *,
    now: datetime | None = None,
    cap: int = MAX_NODES,
) -> RulePreview:
    """What the rule would have raised over the last `PREVIEW_DAYS` days, run as its author over
    stored data. Reads only; it has no store to write to. Its subjects are counted as the author
    first (`match_count`, the access step in the store): past `cap` the preview is refused with
    `limit_exceeded`, never counted in part. Frequencies are counted over the window; a first time
    ever falls within it."""
    ontology = ctx.ontology
    if ontology is None:
        raise RuntimeError("a preview reads the sentence against the deployment's ontology")
    pattern = compile_pattern(sentence, ontology)
    counted = await ctx.graph.match_count(pattern, author, ceiling=cap + 1)
    if counted > cap:
        raise LimitExceededError(LimitExceeded(cap_kind="nodes", cap=cap, would_be=counted))
    stamp = now or datetime.now(UTC)
    window = Interval(valid_from=stamp - timedelta(days=PREVIEW_DAYS), valid_to=stamp)
    words = sentence_words(sentence, ontology)
    if counted == 0:
        return RulePreview(would_raise=0, words=words)
    matched = await ctx.graph.match(pattern.model_copy(update={"limit": cap}), author)
    subjects = sorted((n for n in matched.nodes if n.type == sentence.subject), key=lambda n: n.id)
    _, rest = _split(sentence, ontology)
    hits = await judge_subjects(
        subjects, sentence, author, ctx, window=window, firsts=window, conditions=rest
    )
    examples = [
        PreviewExample(
            node_id=h.node.id, name=node_name(h.node), entity_type=h.node.type, words=h.words
        )
        for h in sorted(hits, key=lambda h: (node_name(h.node), h.node.id))[:PREVIEW_EXAMPLES]
    ]
    return RulePreview(would_raise=len(hits), examples=examples, words=words)


__all__ = [
    "SUBJECT_VAR",
    "Hit",
    "SentenceContext",
    "SentenceRefused",
    "check_sentence",
    "compile_pattern",
    "compile_sentence",
    "hit_signature",
    "judge_sentence",
    "judge_subjects",
    "normalised",
    "preview_sentence",
    "sentence_of",
    "sentence_words",
]
