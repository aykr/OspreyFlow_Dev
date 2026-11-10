"""A rule stored to the standards (`spec/06_DECISIONS.md` ADR-146 decision 3, "Stored to the
standards"): a BPMN 2.0 process of three elements and a DMN 1.3 decision table for its *If*.

**The BPMN** is one process: a start event (the *When*), a business-rule task that calls the
decision (the *If*), and an end event that raises the alert (the *Then*), joined by two sequence
flows, with a drawing (BPMN DI) so any modeller shows it as OspreyFlow does.

**The DMN** is one decision holding one decision table of one rule. The *If*'s conditions on the
subject's properties are its columns, each cell in the one FEEL form the condition's operator is
written in (a string, a list of strings, `> n`, `< n`, a date-and-time range). What DMN cannot
say (the subject's type, a drawn area, a relationship, a frequency, a strength) and the rest of the
rule (when it runs, its limits, its *Then*, its declared dataset) are `osprey:` extension elements
in the places BPMN and DMN keep for them.

**Only what OspreyFlow runs is accepted.** An import holding any other element or attribute of
BPMN, DMN, `osprey:` or another vendor is refused by `UnsupportedElements`, naming each; a file
that is not one rule's (two end events, flows crossed, the two files of two rules, no dataset, a
cell in a form OspreyFlow does not write, a blank the sentence refuses) by `MalformedRuleFile`, in
words. A document type declaration is refused before anything is read (`defusedxml`, no entity is
ever expanded). Nothing here reads a store: the import route checks the rule against its declared
dataset's model and the importer's reach.

The mapping is one function per side (`_rule_dict` written out by `to_bpmn`/`to_dmn`, read back by
`_read_rule`), so the rule model it reads (today `SentenceRuleInput`) changes with one import.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, get_args
from xml.etree.ElementTree import Element, ParseError

import defusedxml.ElementTree as safe_xml
from defusedxml import DefusedXmlException
from pydantic import BaseModel, ValidationError

from schemas.sentences import (
    AreaPoint,
    DrawnArea,
    RuleSchedule,
    RuleSentence,
    SentenceFrequency,
    SentenceRelationship,
    SentenceRuleInput,
    SentenceStrength,
)

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
DC = "http://www.omg.org/spec/DD/20100524/DC"
DI = "http://www.omg.org/spec/DD/20100524/DI"
DMN = "https://www.omg.org/spec/DMN/20191111/MODEL/"
OSPREY = "https://ospreyflow.org/schema/rule/1"

_PREFIX = {BPMN: "bpmn", BPMNDI: "bpmndi", DC: "dc", DI: "di", DMN: "dmn", OSPREY: "osprey"}
_NS_DECLS = {
    "bpmn": f'xmlns:bpmn="{BPMN}" xmlns:bpmndi="{BPMNDI}" xmlns:dc="{DC}" xmlns:di="{DI}" '
    f'xmlns:osprey="{OSPREY}"',
    "dmn": f'xmlns:dmn="{DMN}" xmlns:osprey="{OSPREY}"',
}
_TARGET = "https://ospreyflow.org/rules"
_DECISION_ID = "decision"

#: Every element OspreyFlow runs, by its qualified name, with the attributes it may carry. An
#: `osprey:` attribute is named as `osprey:<name>`; any other is unqualified.
_ALLOWED: dict[str, frozenset[str]] = {
    name: frozenset(attributes)
    for name, attributes in {
        "bpmn:definitions": ("id", "targetNamespace", "exporter", "exporterVersion"),
        "bpmn:process": ("id", "name", "isExecutable"),
        "bpmn:extensionElements": (),
        "bpmn:startEvent": ("id", "name"),
        "bpmn:businessRuleTask": ("id", "name", "implementation", "osprey:decisionRef"),
        "bpmn:endEvent": ("id", "name"),
        "bpmn:sequenceFlow": ("id", "sourceRef", "targetRef"),
        "bpmn:incoming": (),
        "bpmn:outgoing": (),
        "bpmndi:BPMNDiagram": ("id",),
        "bpmndi:BPMNPlane": ("id", "bpmnElement"),
        "bpmndi:BPMNShape": ("id", "bpmnElement"),
        "bpmndi:BPMNEdge": ("id", "bpmnElement"),
        "dc:Bounds": ("x", "y", "width", "height"),
        "di:waypoint": ("x", "y"),
        "dmn:definitions": ("id", "name", "namespace", "exporter", "exporterVersion"),
        "dmn:decision": ("id", "name"),
        "dmn:extensionElements": (),
        "dmn:decisionTable": ("id",),
        "dmn:input": ("id", "label"),
        "dmn:inputExpression": ("id", "typeRef"),
        "dmn:output": ("id", "name", "typeRef"),
        "dmn:rule": ("id",),
        "dmn:inputEntry": ("id",),
        "dmn:outputEntry": ("id",),
        "dmn:text": (),
        "osprey:rule": ("dataset",),
        "osprey:when": ("runs", "onHit"),
        "osprey:schedule": ("every", "hour", "weekday"),
        "osprey:limits": ("budgetMs", "maxMatches"),
        "osprey:raise": ("severity", "team", "teamId", "scope"),
        "osprey:subject": ("type",),
        "osprey:relationship": ("kind", "linkType", "otherType", "steps", "minScore"),
        "osprey:frequency": ("kind", "linkType", "atLeast", "withinDays", "amountProperty", "over"),
        "osprey:strength": ("kind", "linkType", "otherType", "reaches", "scale", "scope"),
        "osprey:area": ("name",),
        "osprey:point": ("lon", "lat"),
    }.items()
}
_ALLOWED_ROOT = {"bpmn": "bpmn:definitions", "dmn": "dmn:definitions"}

#: Where each element may stand: its parent, or for an extension, the element whose
#: `extensionElements` holds it (`owner>extensionElements`). Anything elsewhere is refused by name,
#: so an element OspreyFlow reads in one place is never carried, unread, in another.
_PLACED: dict[str, frozenset[str]] = {
    name: frozenset(parents)
    for name, parents in {
        "bpmn:process": ("bpmn:definitions",),
        "bpmn:extensionElements": ("bpmn:process", "bpmn:businessRuleTask", "bpmn:endEvent"),
        "bpmn:startEvent": ("bpmn:process",),
        "bpmn:businessRuleTask": ("bpmn:process",),
        "bpmn:endEvent": ("bpmn:process",),
        "bpmn:sequenceFlow": ("bpmn:process",),
        "bpmn:incoming": ("bpmn:businessRuleTask", "bpmn:endEvent"),
        "bpmn:outgoing": ("bpmn:startEvent", "bpmn:businessRuleTask"),
        "bpmndi:BPMNDiagram": ("bpmn:definitions",),
        "bpmndi:BPMNPlane": ("bpmndi:BPMNDiagram",),
        "bpmndi:BPMNShape": ("bpmndi:BPMNPlane",),
        "bpmndi:BPMNEdge": ("bpmndi:BPMNPlane",),
        "dc:Bounds": ("bpmndi:BPMNShape",),
        "di:waypoint": ("bpmndi:BPMNEdge",),
        "dmn:decision": ("dmn:definitions",),
        "dmn:extensionElements": ("dmn:decision", "dmn:input"),
        "dmn:decisionTable": ("dmn:decision",),
        "dmn:input": ("dmn:decisionTable",),
        "dmn:output": ("dmn:decisionTable",),
        "dmn:rule": ("dmn:decisionTable",),
        "dmn:inputExpression": ("dmn:input",),
        "dmn:inputEntry": ("dmn:rule",),
        "dmn:outputEntry": ("dmn:rule",),
        "dmn:text": ("dmn:inputExpression", "dmn:inputEntry", "dmn:outputEntry"),
        "osprey:rule": ("bpmn:process>extensionElements",),
        "osprey:when": ("bpmn:process>extensionElements",),
        "osprey:schedule": ("osprey:when",),
        "osprey:limits": ("bpmn:businessRuleTask>extensionElements",),
        "osprey:raise": ("bpmn:endEvent>extensionElements",),
        "osprey:subject": ("dmn:decision>extensionElements",),
        "osprey:relationship": ("dmn:decision>extensionElements",),
        "osprey:frequency": ("dmn:decision>extensionElements",),
        "osprey:strength": ("dmn:decision>extensionElements",),
        "osprey:area": ("dmn:input>extensionElements", "osprey:relationship"),
        "osprey:point": ("osprey:area",),
    }.items()
}


class UnsupportedElements(Exception):
    """An import holding elements or attributes OspreyFlow does not run, each named."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__(
            "These files hold what OspreyFlow does not run, so the rule was not imported: "
            + ", ".join(names)
        )


class MalformedRuleFile(Exception):
    """A file that is not one rule's, said in words."""


@dataclass(frozen=True)
class RuleFile:
    """What the two files hold: the rule, and the dataset it declares."""

    rule: SentenceRuleInput
    dataset_id: str


# --- writing ------------------------------------------------------------------------------------


def _attr(value: object) -> str:
    text = str(value)
    # A tab, line feed or carriage return written bare in an attribute is read back as a space.
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        .replace("\t", "&#9;").replace("\n", "&#10;").replace("\r", "&#13;")
    )  # fmt: skip


def _text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()


def _osprey(tag: str, fields: Mapping[str, Any], children: str = "") -> str:
    """`<osprey:tag a="…"/>` from a model's fields: snake_case to camelCase, `None` left out."""
    attributes = "".join(
        f' {_camel(key)}="{_attr(value)}"' for key, value in fields.items() if value is not None
    )
    if children:
        return f"<osprey:{tag}{attributes}>{children}</osprey:{tag}>"
    return f"<osprey:{tag}{attributes}/>"


def _area(area: Mapping[str, Any]) -> str:
    points = "".join(_osprey("point", p) for p in area["points"])
    return _osprey("area", {"name": area["name"]}, points)


def _rule_dict(rule: SentenceRuleInput) -> dict[str, Any]:
    """The one place the rule model is read on the way out."""
    return rule.model_dump(mode="python")


def _feel_number(value: float) -> str:
    """A FEEL numeric literal: digits and a point, never an exponent (`1e-05` is not FEEL)."""
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{value} is not a number a decision table can hold")
    return format(Decimal(repr(value)), "f")


def _feel_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _feel_time(value: datetime) -> str:
    return f'date and time("{value.isoformat()}")'


def _cell(condition: Mapping[str, Any]) -> tuple[str, str]:
    """A condition's DMN cell and its column's type."""
    op = condition["op"]
    if op == "equals":
        return _feel_string(condition["value"]), "string"
    if op == "one_of":
        return ",".join(_feel_string(v) for v in condition["values"]), "string"
    if op == "above":
        return f"> {_feel_number(condition['value'])}", "number"
    if op == "below":
        return f"< {_feel_number(condition['value'])}", "number"
    if op == "within_time":
        start, end = condition["start"], condition["end"]
        if start is not None and end is not None:
            return f"[{_feel_time(start)}..{_feel_time(end)}]", "date and time"
        if start is not None:
            return f">= {_feel_time(start)}", "date and time"
        return f"<= {_feel_time(end)}", "date and time"
    return "-", "string"  # within_area: the area is the column's own osprey:area


def _when_words(sentence: Mapping[str, Any]) -> str:
    runs = sentence["runs"]
    if runs == "pre_commit":
        return "As data loads, before commit"
    if runs == "post_commit":
        return "As data loads, after commit"
    schedule = sentence["schedule"]
    days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    when = "Every day" if schedule["every"] == "daily" else f"Every {days[schedule['weekday'] - 1]}"
    return f"{when} at {schedule['hour']:02d}:00"


def to_bpmn(rule: SentenceRuleInput, *, dataset_id: str) -> str:
    """The rule's process: its *When*, the task calling its decision, and its *Then*."""
    data = _rule_dict(rule)
    sentence = data["sentence"]
    schedule = sentence["schedule"]
    when = _osprey(
        "when",
        {"runs": sentence["runs"], "on_hit": sentence["on_hit"]},
        _osprey("schedule", schedule) if schedule is not None else "",
    )
    then = {"severity": sentence["severity"], "team": sentence["team"]}
    # lane/rules' L2.10 names a team by its role id (ADR-146 decision 8); written when present.
    if sentence.get("team_id") is not None:
        then["team_id"] = sentence["team_id"]
    raise_ = _osprey("raise", {**then, "scope": sentence["scope"]})
    limits = _osprey("limits", {"budget_ms": data["budget_ms"], "max_matches": data["max_matches"]})
    subject = _attr(sentence["subject"])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<bpmn:definitions {_NS_DECLS["bpmn"]} id="definitions" targetNamespace="{_TARGET}" '
        'exporter="OspreyFlow" exporterVersion="1">'
        f'<bpmn:process id="rule" name="{_attr(data["name"])}" isExecutable="true">'
        "<bpmn:extensionElements>"
        f"{_osprey('rule', {'dataset': dataset_id})}{when}"
        "</bpmn:extensionElements>"
        f'<bpmn:startEvent id="when" name="{_attr(_when_words(sentence))}">'
        "<bpmn:outgoing>flow_1</bpmn:outgoing></bpmn:startEvent>"
        '<bpmn:sequenceFlow id="flow_1" sourceRef="when" targetRef="if"/>'
        f'<bpmn:businessRuleTask id="if" name="If a {subject} meets the conditions" '
        f'implementation="{DMN}" osprey:decisionRef="{_DECISION_ID}">'
        f"<bpmn:extensionElements>{limits}</bpmn:extensionElements>"
        "<bpmn:incoming>flow_1</bpmn:incoming><bpmn:outgoing>flow_2</bpmn:outgoing>"
        "</bpmn:businessRuleTask>"
        '<bpmn:sequenceFlow id="flow_2" sourceRef="if" targetRef="then"/>'
        f'<bpmn:endEvent id="then" name="Raise a {_attr(sentence["severity"])} alert">'
        f"<bpmn:extensionElements>{raise_}</bpmn:extensionElements>"
        "<bpmn:incoming>flow_2</bpmn:incoming></bpmn:endEvent>"
        "</bpmn:process>"
        '<bpmndi:BPMNDiagram id="diagram"><bpmndi:BPMNPlane id="plane" bpmnElement="rule">'
        '<bpmndi:BPMNShape id="when_di" bpmnElement="when">'
        '<dc:Bounds x="100" y="100" width="36" height="36"/></bpmndi:BPMNShape>'
        '<bpmndi:BPMNShape id="if_di" bpmnElement="if">'
        '<dc:Bounds x="190" y="78" width="120" height="80"/></bpmndi:BPMNShape>'
        '<bpmndi:BPMNShape id="then_di" bpmnElement="then">'
        '<dc:Bounds x="364" y="100" width="36" height="36"/></bpmndi:BPMNShape>'
        '<bpmndi:BPMNEdge id="flow_1_di" bpmnElement="flow_1">'
        '<di:waypoint x="136" y="118"/><di:waypoint x="190" y="118"/></bpmndi:BPMNEdge>'
        '<bpmndi:BPMNEdge id="flow_2_di" bpmnElement="flow_2">'
        '<di:waypoint x="310" y="118"/><di:waypoint x="364" y="118"/></bpmndi:BPMNEdge>'
        "</bpmndi:BPMNPlane></bpmndi:BPMNDiagram>"
        "</bpmn:definitions>\n"
    )


def to_dmn(rule: SentenceRuleInput) -> str:
    """The rule's *If* as a decision table: one column per property condition, one rule."""
    data = _rule_dict(rule)
    sentence = data["sentence"]
    extensions = _osprey("subject", {"type": sentence["subject"]})
    relationship = sentence["relationship"]
    if relationship is not None:
        area = relationship.pop("area", None)
        extensions += _osprey("relationship", relationship, _area(area) if area else "")
    for part in ("frequency", "strength"):
        if sentence[part] is not None:
            extensions += _osprey(part, sentence[part])
    inputs = entries = ""
    for n, condition in enumerate(sentence["conditions"], start=1):
        cell, type_ref = _cell(condition)
        prop = _text(condition["property"])
        own = (
            f"<dmn:extensionElements>{_area(condition['area'])}</dmn:extensionElements>"
            if condition["op"] == "within_area"
            else ""
        )
        inputs += (
            f'<dmn:input id="input_{n}" label="{_attr(condition["property"])}">{own}'
            f'<dmn:inputExpression id="input_{n}_expression" typeRef="{type_ref}">'
            f"<dmn:text>{prop}</dmn:text></dmn:inputExpression></dmn:input>"
        )
        entries += (
            f'<dmn:inputEntry id="rule_1_input_{n}">'
            f"<dmn:text>{_text(cell)}</dmn:text></dmn:inputEntry>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<dmn:definitions {_NS_DECLS["dmn"]} id="definitions" name="{_attr(data["name"])}" '
        f'namespace="{_TARGET}" exporter="OspreyFlow" exporterVersion="1">'
        f'<dmn:decision id="{_DECISION_ID}" name="If">'
        f"<dmn:extensionElements>{extensions}</dmn:extensionElements>"
        f'<dmn:decisionTable id="table">{inputs}'
        '<dmn:output id="output" name="raise" typeRef="boolean"/>'
        f'<dmn:rule id="rule_1">{entries}'
        '<dmn:outputEntry id="rule_1_output"><dmn:text>true</dmn:text></dmn:outputEntry>'
        "</dmn:rule></dmn:decisionTable></dmn:decision></dmn:definitions>\n"
    )


@dataclass(frozen=True)
class StoredRuleFiles:
    """A rule version's two files, as they are stored beside it and as Export serves them: the
    UTF-8 bytes `to_bpmn` and `to_dmn` wrote, never rendered again (ADR-146 Amendment 5)."""

    bpmn: bytes
    dmn: bytes


def rule_files(rule: SentenceRuleInput, *, dataset_id: str) -> StoredRuleFiles:
    """What rules' save writes beside each rule version, in the same transaction: the two files,
    exactly as Export then serves them. A rule the files cannot hold (a number no decision table
    holds) raises `ValueError`, so the save is refused rather than stored without its files."""
    return StoredRuleFiles(
        bpmn=to_bpmn(rule, dataset_id=dataset_id).encode(), dmn=to_dmn(rule).encode()
    )


# --- reading ------------------------------------------------------------------------------------


def _qualified(name: str) -> str:
    if name.startswith("{"):
        uri, local = name[1:].split("}", 1)
        prefix = _PREFIX.get(uri)
        return f"{prefix}:{local}" if prefix else name
    return name


def _parse(data: bytes, kind: str) -> Element:
    label = {"bpmn": "a BPMN 2.0", "dmn": "a DMN 1.3"}[kind]
    try:
        root = safe_xml.fromstring(data, forbid_dtd=True)
    except DefusedXmlException:
        raise MalformedRuleFile(
            f"The .{kind} file has a document type declaration or an entity, which a rule file "
            "never needs; nothing in it was read"
        ) from None
    except ParseError as exc:
        raise MalformedRuleFile(
            f"The .{kind} file is not {label} document: it is not well-formed XML ({exc})"
        ) from None
    if _qualified(root.tag) != _ALLOWED_ROOT[kind]:
        raise MalformedRuleFile(
            f"The .{kind} file is not {label} document: it begins with {_qualified(root.tag)}"
        )
    return root


def _unsupported(root: Element) -> list[str]:
    found: list[str] = []
    parents = {child: parent for parent in root.iter() for child in parent}
    for element in root.iter():
        name = _qualified(element.tag)
        allowed = _ALLOWED.get(name)
        if allowed is None:
            found.append(name)
            continue
        parent = parents.get(element)
        if parent is not None:
            where = _qualified(parent.tag)
            if where.endswith(":extensionElements") and parent in parents:
                where = f"{_qualified(parents[parent].tag)}>extensionElements"
            if where not in _PLACED.get(name, frozenset()):
                found.append(f"{name} (inside {where.replace('>', ' ')})")
        for attribute in element.attrib:
            attr = _qualified(attribute)
            if attr not in allowed:
                found.append(f"{attr} (on {name})")
    return list(dict.fromkeys(found))


def _children(element: Element, name: str) -> list[Element]:
    return [c for c in element if _qualified(c.tag) == name]


def _one(element: Element, name: str, what: str, file: str) -> Element:
    found = _children(element, name)
    if len(found) != 1:
        raise MalformedRuleFile(f"The .{file} file must hold {what}; it holds {len(found)}")
    return found[0]


def _variant(union: Any, kind: str | None) -> type[BaseModel] | None:
    """The member of a discriminated union whose `kind` is `kind`, or `None` for no such kind
    (then the model's own validation refuses it, in words)."""
    for member in get_args(get_args(union)[0]):
        if member.model_fields["kind"].default == kind:
            return member  # type: ignore[no-any-return]
    return None


def _fields(element: Element, model: type[BaseModel] | None = None) -> dict[str, str]:
    """An `osprey:` element's attributes as the model's fields. An attribute the model has no
    field for is refused by name: the model would ignore it, and the rule would come back without
    what the file said (a team named by a schema that has no team yet, a link type on a hotlist)."""
    fields = {_snake(_qualified(k).removeprefix("osprey:")): v for k, v in element.attrib.items()}
    if model is not None:
        unread = [k for k in fields if k not in model.model_fields]
        if unread:
            name = _qualified(element.tag)
            raise UnsupportedElements([f"osprey:{_camel(k)} (on {name})" for k in unread])
    return fields


def _read_area(element: Element, file: str) -> dict[str, Any]:
    area = _one(element, "osprey:area", "one drawn area", file)
    points = [_fields(p, AreaPoint) for p in _children(area, "osprey:point")]
    return {**_fields(area, DrawnArea), "points": points}


_STRINGS = re.compile(r'"(?:[^"\\]|\\.)*"(?:,"(?:[^"\\]|\\.)*")*')
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
_NUMBER = re.compile(r"([<>]) (-?\d+(?:\.\d+)?)")
_TIME = r'date and time\("([^"]+)"\)'
_RANGE = re.compile(rf"\[{_TIME}\.\.{_TIME}\]")
_FROM = re.compile(rf">= {_TIME}")
_UNTIL = re.compile(rf"<= {_TIME}")


def _read_cell(prop: str, cell: str, area: dict[str, Any] | None) -> dict[str, Any]:
    if area is not None:
        if cell != "-":
            raise MalformedRuleFile(
                f"The condition on {prop} is a drawn area, so its cell is '-'; it reads '{cell}'"
            )
        return {"op": "within_area", "property": prop, "area": area}
    if match := _RANGE.fullmatch(cell):
        return {"op": "within_time", "property": prop, "start": match[1], "end": match[2]}
    if match := _FROM.fullmatch(cell):
        return {"op": "within_time", "property": prop, "start": match[1]}
    if match := _UNTIL.fullmatch(cell):
        return {"op": "within_time", "property": prop, "end": match[1]}
    if match := _NUMBER.fullmatch(cell):
        return {"op": "above" if match[1] == ">" else "below", "property": prop, "value": match[2]}
    if _STRINGS.fullmatch(cell):
        values = [re.sub(r"\\(.)", r"\1", v) for v in _STRING.findall(cell)]
        if len(values) == 1:
            return {"op": "equals", "property": prop, "value": values[0]}
        return {"op": "one_of", "property": prop, "values": values}
    raise MalformedRuleFile(
        f"The condition on {prop} reads '{cell}', which is not one of the forms OspreyFlow writes "
        "(a word in quotes, a list of them, > or < a number, or a date-and-time range); a rule "
        "file is never read as an expression"
    )


def _read_bpmn(root: Element) -> tuple[str, str, dict[str, Any], dict[str, str], str]:
    """The process: its name, its dataset, its *When* and *Then*, its limits and its decision."""
    process = _one(root, "bpmn:process", "one process", "bpmn")
    counts = {
        "start event": _children(process, "bpmn:startEvent"),
        "business-rule task": _children(process, "bpmn:businessRuleTask"),
        "end event": _children(process, "bpmn:endEvent"),
    }
    for what, found in counts.items():
        if len(found) != 1:
            raise MalformedRuleFile(
                "A rule's process is one start event, one business-rule task and one end event; "
                f"this one has {len(found)} {what}s"
            )
    start, task, end = (found[0] for found in counts.values())
    flows = {
        (f.get("sourceRef"), f.get("targetRef")) for f in _children(process, "bpmn:sequenceFlow")
    }
    wanted = {(start.get("id"), task.get("id")), (task.get("id"), end.get("id"))}
    if flows != wanted or len(_children(process, "bpmn:sequenceFlow")) != 2:
        raise MalformedRuleFile(
            "The process's three elements are not joined start to task to end by two flows"
        )
    extensions = _one(
        process, "bpmn:extensionElements", "one set of the process's extensions", "bpmn"
    )
    dataset = _fields(_one(extensions, "osprey:rule", "one osprey:rule", "bpmn")).get("dataset")
    if not dataset:
        raise MalformedRuleFile(
            "The .bpmn file names no dataset: a rule always works on one declared dataset"
        )
    when_el = _one(extensions, "osprey:when", "one osprey:when", "bpmn")
    when: dict[str, Any] = _fields(when_el, RuleSentence)
    schedules = _children(when_el, "osprey:schedule")
    if len(schedules) > 1:
        raise MalformedRuleFile("The rule's osprey:when holds more than one schedule")
    when["schedule"] = _fields(schedules[0], RuleSchedule) if schedules else None
    task_ext = _one(task, "bpmn:extensionElements", "the task's extensions", "bpmn")
    limits = _fields(
        _one(task_ext, "osprey:limits", "one osprey:limits", "bpmn"), SentenceRuleInput
    )
    end_ext = _one(end, "bpmn:extensionElements", "the end event's extensions", "bpmn")
    then = _fields(_one(end_ext, "osprey:raise", "one osprey:raise", "bpmn"), RuleSentence)
    decision_ref = task.get(f"{{{OSPREY}}}decisionRef") or ""
    return process.get("name") or "", dataset, {**when, **then}, limits, decision_ref


def _read_dmn(root: Element, decision_ref: str) -> tuple[str, dict[str, Any]]:
    """The decision: its name and the *If*."""
    decision = _one(root, "dmn:decision", "one decision", "dmn")
    if decision.get("id") != decision_ref:
        raise MalformedRuleFile(
            "The two files are not of one rule: the task calls a decision the .dmn file "
            "does not hold"
        )
    extensions = _one(decision, "dmn:extensionElements", "the decision's extensions", "dmn")
    sentence: dict[str, Any] = {
        "subject": _fields(_one(extensions, "osprey:subject", "one osprey:subject", "dmn")).get(
            "type"
        )
    }
    for part in ("relationship", "frequency", "strength"):
        found = _children(extensions, f"osprey:{part}")
        if len(found) > 1:
            raise MalformedRuleFile(f"The decision holds more than one osprey:{part}")
        if found:
            unions = {"relationship": SentenceRelationship, "frequency": SentenceFrequency,
                      "strength": SentenceStrength}  # fmt: skip
            model = _variant(unions[part], found[0].get("kind"))
            sentence[part] = _fields(found[0], model)
            if _children(found[0], "osprey:area"):
                sentence[part]["area"] = _read_area(found[0], "dmn")
    table = _one(decision, "dmn:decisionTable", "one decision table", "dmn")
    rows = _children(table, "dmn:rule")
    inputs = _children(table, "dmn:input")
    if len(rows) != 1:
        raise MalformedRuleFile(f"A rule's decision table has one rule; this one has {len(rows)}")
    cells = _children(rows[0], "dmn:inputEntry")
    if len(cells) != len(inputs):
        raise MalformedRuleFile("The decision table's rule does not fill every column")
    if len(_children(table, "dmn:output")) != 1:
        raise MalformedRuleFile(
            "A rule's decision table has one output, whether to raise the alert"
        )
    outputs = [_children(o, "dmn:text") for o in _children(rows[0], "dmn:outputEntry")]
    if len(outputs) != 1 or [t.text for t in outputs[0]] != ["true"]:
        raise MalformedRuleFile(
            "The decision table's rule must raise the alert: its output is true"
        )
    conditions = []
    for column, cell in zip(inputs, cells, strict=True):
        expression = _one(column, "dmn:inputExpression", "one input expression per column", "dmn")
        prop = (_one(expression, "dmn:text", "the column's property", "dmn").text or "").strip()
        own = _children(column, "dmn:extensionElements")
        area = _read_area(own[0], "dmn") if own else None
        text = (_one(cell, "dmn:text", "one cell text", "dmn").text or "").strip()
        conditions.append(_read_cell(prop, text, area))
    sentence["conditions"] = conditions
    return root.get("name") or "", sentence


def _read_rule(
    name: str, when_then: dict[str, Any], limits: dict[str, str], sentence: dict[str, Any]
) -> SentenceRuleInput:
    """The one place the rule model is built on the way in."""
    try:
        return SentenceRuleInput.model_validate(
            {"name": name, "sentence": {**sentence, **when_then}, **limits}
        )
    except ValidationError as exc:
        said = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'the rule'}: {e['msg']}" for e in exc.errors()
        )
        raise MalformedRuleFile(f"The rule in these files is refused: {said}") from None


def from_files(bpmn: bytes, dmn: bytes) -> RuleFile:
    """The rule the two files hold, or a refusal naming what is wrong with them."""
    bpmn_root, dmn_root = _parse(bpmn, "bpmn"), _parse(dmn, "dmn")
    unsupported = _unsupported(bpmn_root) + _unsupported(dmn_root)
    if unsupported:
        raise UnsupportedElements(list(dict.fromkeys(unsupported)))
    name, dataset, when_then, limits, decision_ref = _read_bpmn(bpmn_root)
    dmn_name, sentence = _read_dmn(dmn_root, decision_ref)
    if dmn_name != name:
        raise MalformedRuleFile(
            f"The two files are not of one rule: the process is '{name}' and the decision "
            f"'{dmn_name}'"
        )
    return RuleFile(rule=_read_rule(name, when_then, limits, sentence), dataset_id=dataset)
