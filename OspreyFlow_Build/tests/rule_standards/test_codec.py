"""A rule stored to the standards (`spec/06_DECISIONS.md` ADR-146 decision 3, "Stored to the
standards"): a BPMN 2.0 process of three elements and a DMN decision table for its *If*, exported
and imported back to the same rule; an import holding anything OspreyFlow does not run refused,
naming it.

Rule 15: every refusal here is planted in a file `to_bpmn`/`to_dmn` really wrote, the shape
`from_files` receives at the import route, never a hand-written approximation.

What a mistake would do, and the case that catches it:
- a blank of the sentence lost or changed on the way: `test_export_then_import_gives_the_same_rule`,
  one case per shape of every blank;
- an element OspreyFlow does not run carried in silently:
  `test_a_bpmn_element_it_does_not_run_is_refused_by_name`, and its DMN, `osprey:` element
  and attribute siblings;
- a sixth element, or the three not joined start to end:
  `test_the_process_must_be_the_three_elements_in_order`;
- a file naming no dataset accepted: `test_a_rule_file_naming_no_dataset_is_refused_in_words`;
- a DTD or entity expanded: `test_a_document_type_declaration_is_refused`;
- a condition's value read by an expression: `test_a_dmn_cell_outside_the_forms_written_is_refused`.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rule_standards import (
    MalformedRuleFile,
    RuleFile,
    UnsupportedElements,
    from_files,
    rule_files,
    to_bpmn,
    to_dmn,
)
from schemas.sentences import RuleSentence, SentenceRuleInput

DATASET = "ds-prison"

AREA = {
    "name": "the port area",
    "points": [{"lon": -1.5, "lat": 50.9}, {"lon": -1.4, "lat": 50.9}, {"lon": -1.4, "lat": 51.0}],
}

SENTENCES: dict[str, dict[str, object]] = {
    "the least": {"subject": "Person"},
    "every condition": {
        "subject": "Person",
        "conditions": [
            {"op": "equals", "property": "family_name", "value": 'O"Neil \\ the "elder"'},
            {"op": "one_of", "property": "nationality", "values": ["GB", "IE", "a, b"]},
            {"op": "above", "property": "age", "value": 17.5},
            {"op": "below", "property": "risk", "value": -0.000123},
            {
                "op": "within_time",
                "property": "seen_at",
                "start": datetime(2026, 1, 1, tzinfo=UTC),
                "end": datetime(2026, 3, 1, 12, 30, tzinfo=UTC),
            },
        ],
        "severity": "high",
        "team": "my_team",
    },
    "a drawn area": {
        "subject": "Location",
        "conditions": [
            {"op": "within_area", "property": "geometry_ref", "area": AREA},
            {"op": "equals", "property": "kind", "value": "port"},
        ],
    },
    "a window open at its end": {
        "subject": "Person",
        "conditions": [
            {"op": "within_time", "property": "seen_at", "start": datetime(2026, 1, 1, tzinfo=UTC)}
        ],
    },
    "a window open at its start": {
        "subject": "Person",
        "conditions": [
            {"op": "within_time", "property": "seen_at", "end": datetime(2026, 1, 1, tzinfo=UTC)}
        ],
    },
    "linked": {
        "subject": "Person",
        "relationship": {"kind": "linked", "link_type": "KNOWS", "other_type": "Person"},
    },
    "linked to anything": {
        "subject": "Person",
        "relationship": {"kind": "linked", "link_type": "KNOWS"},
    },
    "within steps": {
        "subject": "Person",
        "relationship": {"kind": "within_steps", "steps": 3, "other_type": "Vehicle"},
    },
    "at a location": {
        "subject": "Person",
        "relationship": {"kind": "at_location", "link_type": "SEEN_AT", "area": AREA},
    },
    "on a hotlist": {
        "subject": "Phone",
        "relationship": {"kind": "on_hotlist"},
        "scope": "just_me",
    },
    "on a screening list": {
        "subject": "Person",
        "relationship": {"kind": "on_screening_list", "min_score": 0.85},
    },
    "a count": {
        "subject": "Account",
        "frequency": {"kind": "count", "link_type": "PAID", "at_least": 5, "within_days": 30},
    },
    "an amount": {
        "subject": "Account",
        "frequency": {
            "kind": "amount",
            "link_type": "PAID",
            "amount_property": "amount",
            "over": 9999.99,
            "within_days": 7,
        },
    },
    "a first time": {
        "subject": "Account",
        "frequency": {"kind": "first_time", "link_type": "PAID"},
    },
    "a strength": {
        "subject": "Person",
        "strength": {
            "kind": "connection_strength",
            "link_type": "KNOWS",
            "other_type": "Person",
            "reaches": 0.75,
        },
    },
    "a strength on the client's scale": {
        "subject": "Person",
        "strength": {"kind": "connection_strength", "reaches": 4.5, "scale": "client"},
    },
    "a rarity": {
        "subject": "Person",
        "strength": {"kind": "shared_attribute_rarity", "reaches": 12, "scope": "case"},
    },
    "before commit, held": {
        "subject": "Person",
        "conditions": [{"op": "equals", "property": "family_name", "value": "Okafor"}],
        "runs": "pre_commit",
        "on_hit": "hold",
    },
    "daily": {"subject": "Person", "runs": "schedule", "schedule": {"every": "daily", "hour": 23}},
    "weekly": {
        "subject": "Person",
        "runs": "schedule",
        "schedule": {"every": "weekly", "hour": 0, "weekday": 7},
        "severity": "low",
    },
    "the whole deployment": {"subject": "Person", "scope": "deployment"},
}


def _rule(
    shape: str = "every condition", name: str = "Prison contacts & <visitors>"
) -> SentenceRuleInput:
    return SentenceRuleInput(
        name=name,
        sentence=RuleSentence.model_validate(SENTENCES[shape]),
        budget_ms=7000,
        max_matches=150,
    )


def _files(rule: SentenceRuleInput | None = None) -> tuple[str, str]:
    rule = rule or _rule()
    return to_bpmn(rule, dataset_id=DATASET), to_dmn(rule)


@pytest.mark.parametrize("shape", sorted(SENTENCES))
def test_export_then_import_gives_the_same_rule(shape: str) -> None:
    rule = _rule(shape)
    bpmn, dmn = _files(rule)
    back = from_files(bpmn.encode(), dmn.encode())
    assert back == RuleFile(rule=rule, dataset_id=DATASET)


@pytest.mark.skipif(
    "team_id" not in RuleSentence.model_fields, reason="a named team arrives with lane/rules' L2.10"
)
def test_a_rule_for_a_named_team_keeps_its_team() -> None:
    sentence = RuleSentence.model_validate(
        {"subject": "Person", "team": "team", "team_id": "role-7"}
    )
    rule = SentenceRuleInput(name="Team rule", sentence=sentence)
    bpmn, dmn = _files(rule)
    assert 'teamId="role-7"' in bpmn
    assert from_files(bpmn.encode(), dmn.encode()) == RuleFile(rule=rule, dataset_id=DATASET)


def test_the_files_are_the_three_elements_and_one_decision_table() -> None:
    bpmn, dmn = _files()
    assert bpmn.count("<bpmn:startEvent ") == 1
    assert bpmn.count("<bpmn:businessRuleTask ") == 1
    assert bpmn.count("<bpmn:endEvent ") == 1
    assert 'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"' in bpmn
    assert dmn.count("<dmn:decisionTable ") == 1
    assert 'xmlns:dmn="https://www.omg.org/spec/DMN/20191111/MODEL/"' in dmn
    # The If's property conditions are the table's columns, as DMN says them.
    assert "<dmn:text>&gt; 17.5</dmn:text>" in dmn
    assert '<dmn:text>"GB","IE","a, b"</dmn:text>' in dmn


def _plant(xml: str, after: str, planted: str) -> bytes:
    assert after in xml, f"the exported file no longer holds {after!r}; the plant must move with it"
    return xml.replace(after, after + planted, 1).encode()


def test_a_bpmn_element_it_does_not_run_is_refused_by_name() -> None:
    bpmn, dmn = _files()
    planted = _plant(
        bpmn,
        "</bpmn:businessRuleTask>",
        '<bpmn:exclusiveGateway id="g1" name="Route"/><bpmn:userTask id="u1"/>',
    )
    with pytest.raises(UnsupportedElements) as refused:
        from_files(planted, dmn.encode())
    assert refused.value.names == ["bpmn:exclusiveGateway", "bpmn:userTask"]
    assert "bpmn:exclusiveGateway" in str(refused.value)


def test_a_dmn_element_it_does_not_run_is_refused_by_name() -> None:
    bpmn, dmn = _files()
    planted = _plant(dmn, "</dmn:decision>", '<dmn:businessKnowledgeModel id="bkm"/>')
    with pytest.raises(UnsupportedElements) as refused:
        from_files(bpmn.encode(), planted)
    assert refused.value.names == ["dmn:businessKnowledgeModel"]


def test_an_unknown_osprey_element_or_attribute_is_refused_by_name() -> None:
    bpmn, dmn = _files()
    element = _plant(bpmn, "<bpmn:extensionElements>", '<osprey:escalate after="3"/>')
    with pytest.raises(UnsupportedElements) as refused:
        from_files(element, dmn.encode())
    assert refused.value.names == ["osprey:escalate"]
    attribute = bpmn.replace("<osprey:raise ", '<osprey:raise osprey:copyTo="ops" ', 1).encode()
    with pytest.raises(UnsupportedElements) as refused:
        from_files(attribute, dmn.encode())
    assert refused.value.names == ["osprey:copyTo (on osprey:raise)"]


def test_another_vendors_extension_is_refused_by_name() -> None:
    bpmn, dmn = _files()
    planted = bpmn.replace(
        "<bpmn:definitions ",
        '<bpmn:definitions xmlns:camunda="http://camunda.org/schema/1.0/bpmn" ',
        1,
    ).replace("<bpmn:businessRuleTask ", '<bpmn:businessRuleTask camunda:asyncBefore="true" ', 1)
    with pytest.raises(UnsupportedElements) as refused:
        from_files(planted.encode(), dmn.encode())
    assert refused.value.names == [
        "{http://camunda.org/schema/1.0/bpmn}asyncBefore (on bpmn:businessRuleTask)"
    ]


def test_the_process_must_be_the_three_elements_in_order() -> None:
    bpmn, dmn = _files()
    second_end = _plant(bpmn, "</bpmn:endEvent>", '<bpmn:endEvent id="then_2"/>')
    with pytest.raises(MalformedRuleFile, match="one end event"):
        from_files(second_end, dmn.encode())
    crossed = re.sub(
        r'(<bpmn:sequenceFlow id="flow_2" sourceRef=")if(")', r"\1when\2", bpmn, count=1
    )
    assert crossed != bpmn
    with pytest.raises(MalformedRuleFile, match="joined"):
        from_files(crossed.encode(), dmn.encode())


def test_a_rule_file_naming_no_dataset_is_refused_in_words() -> None:
    bpmn, dmn = _files()
    planted = re.sub(r'<osprey:rule dataset="[^"]*"/>', "<osprey:rule/>", bpmn, count=1)
    assert planted != bpmn
    with pytest.raises(MalformedRuleFile, match="names no dataset"):
        from_files(planted.encode(), dmn.encode())


def test_the_two_files_must_be_of_one_rule() -> None:
    bpmn, _ = _files()
    _, other = _files(_rule(name="Another rule"))
    with pytest.raises(MalformedRuleFile, match="not of one rule"):
        from_files(bpmn.encode(), other.encode())


def test_a_document_type_declaration_is_refused() -> None:
    bpmn, dmn = _files()
    planted = bpmn.replace(
        "<bpmn:definitions ", '<!DOCTYPE d [<!ENTITY x "xx">]><bpmn:definitions ', 1
    ).encode()
    with pytest.raises(MalformedRuleFile, match="declaration"):
        from_files(planted, dmn.encode())


def test_a_file_that_is_not_xml_is_refused_in_words() -> None:
    _, dmn = _files()
    with pytest.raises(MalformedRuleFile, match="not a BPMN"):
        from_files(b"not xml at all", dmn.encode())


def test_a_dmn_cell_outside_the_forms_written_is_refused() -> None:
    bpmn, dmn = _files()
    planted = dmn.replace("<dmn:text>&gt; 17.5</dmn:text>", "<dmn:text>&gt; age * 2</dmn:text>", 1)
    assert planted != dmn
    with pytest.raises(MalformedRuleFile, match="age"):
        from_files(bpmn.encode(), planted.encode())


def test_a_blank_the_sentence_refuses_is_refused_in_words() -> None:
    bpmn, dmn = _files(_rule("daily"))
    planted = bpmn.replace('hour="23"', 'hour="25"', 1)
    assert planted != bpmn
    with pytest.raises(MalformedRuleFile, match="hour"):
        from_files(planted.encode(), dmn.encode())


#: The `.bpmn` the workspace's *Show as BPMN* tests and harness draw: the codec's own output, so the
#: drawing is tested against what the export route really sends (rule 15), never a hand-written file.
WORKSPACE_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "OspreyFlow_Core/apps/workspace/src/alerts/ruleStandards/fixtures/visits-to-listed-people.bpmn"
)


def workspace_fixture_rule() -> SentenceRuleInput:
    sentence = RuleSentence.model_validate({
        "subject": "Person",
        "conditions": [{"op": "one_of", "property": "listing", "values": ["sanction", "pep"]}],
        "frequency": {"kind": "count", "link_type": "VISITED", "at_least": 3, "within_days": 7},
        "severity": "high",
    })  # fmt: skip
    return SentenceRuleInput(name="Visits to listed people", sentence=sentence)


def test_the_workspace_fixture_is_the_codecs_own_output() -> None:
    written = to_bpmn(workspace_fixture_rule(), dataset_id="ds-prison-visits")
    if os.environ.get("OSPREY_WRITE_FIXTURES") == "1":
        WORKSPACE_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        WORKSPACE_FIXTURE.write_text(written)
    assert WORKSPACE_FIXTURE.read_text() == written, (
        "the workspace's BPMN fixture is not what the codec writes; rewrite it with "
        "OSPREY_WRITE_FIXTURES=1"
    )


def test_a_bare_document_type_declaration_is_refused() -> None:
    # No entity: only `forbid_dtd` refuses this one (an entity is refused by defusedxml anyway).
    bpmn, dmn = _files()
    planted = bpmn.replace("<bpmn:definitions ", "<!DOCTYPE definitions><bpmn:definitions ", 1)
    with pytest.raises(MalformedRuleFile, match="declaration"):
        from_files(planted.encode(), dmn.encode())


def test_a_name_with_a_tab_or_a_line_break_comes_back_the_same() -> None:
    rule = _rule("the least", name="Visits\tafter\nhours\r")
    bpmn, dmn = _files(rule)
    assert from_files(bpmn.encode(), dmn.encode()).rule == rule


@pytest.mark.parametrize("value", [1e-05, 1.5e20, -0.0, 12345678.125])
def test_a_number_is_a_feel_literal_and_comes_back_the_same(value: float) -> None:
    sentence = RuleSentence.model_validate(
        {"subject": "Account", "conditions": [{"op": "above", "property": "balance", "value": value}]}
    )
    rule = SentenceRuleInput(name="n", sentence=sentence)
    bpmn, dmn = _files(rule)
    (cell,) = re.findall(r'<dmn:inputEntry id="rule_1_input_1"><dmn:text>([^<]*)</dmn:text>', dmn)
    assert re.fullmatch(r"&gt; -?\d+(\.\d+)?", cell), cell
    assert from_files(bpmn.encode(), dmn.encode()).rule == rule


def test_a_number_a_table_cannot_hold_is_refused_at_export() -> None:
    sentence = RuleSentence.model_validate(
        {"subject": "Account", "conditions": [{"op": "below", "property": "balance", "value": "inf"}]}
    )
    with pytest.raises(ValueError, match="not a number"):
        to_dmn(SentenceRuleInput(name="n", sentence=sentence))


def test_a_time_column_is_typed_as_dmn_names_it() -> None:
    _, dmn = _files()
    assert 'typeRef="date and time"' in dmn and "dateTime" not in dmn


def test_an_element_out_of_its_place_is_refused_by_name() -> None:
    bpmn, dmn = _files()
    in_the_drawing = _plant(bpmn, '<bpmndi:BPMNPlane id="plane" bpmnElement="rule">', '<bpmn:endEvent id="x"/>')
    with pytest.raises(UnsupportedElements) as refused:
        from_files(in_the_drawing, dmn.encode())
    assert refused.value.names == ["bpmn:endEvent (inside bpmndi:BPMNPlane)"]
    stray = _plant(bpmn, "<bpmn:extensionElements>", '<osprey:raise severity="low" team="case" scope="this_case"/>')
    with pytest.raises(UnsupportedElements) as refused:
        from_files(stray, dmn.encode())
    assert refused.value.names == ["osprey:raise (inside bpmn:process extensionElements)"]


def test_a_second_output_is_refused() -> None:
    bpmn, dmn = _files()
    planted = _plant(dmn, '<dmn:output id="output" name="raise" typeRef="boolean"/>',
                     '<dmn:output id="output_2" name="also" typeRef="boolean"/>')
    with pytest.raises(MalformedRuleFile, match="one output"):
        from_files(bpmn.encode(), planted)


def test_an_attribute_the_rule_would_drop_is_refused_by_name() -> None:
    bpmn, dmn = _files(_rule("on a hotlist"))
    linked = dmn.replace('<osprey:relationship kind="on_hotlist"/>',
                         '<osprey:relationship kind="on_hotlist" linkType="KNOWS"/>', 1)
    assert linked != dmn
    with pytest.raises(UnsupportedElements) as refused:
        from_files(bpmn.encode(), linked.encode())
    assert refused.value.names == ["osprey:linkType (on osprey:relationship)"]
    bpmn, dmn = _files(_rule("a rarity"))
    scaled = dmn.replace('kind="shared_attribute_rarity"', 'kind="shared_attribute_rarity" scale="client"', 1)
    assert scaled != dmn
    with pytest.raises(UnsupportedElements) as refused:
        from_files(bpmn.encode(), scaled.encode())
    assert refused.value.names == ["osprey:scale (on osprey:strength)"]


@pytest.mark.skipif("team_id" in RuleSentence.model_fields, reason="the sentence names a team since L2.10")
def test_a_team_is_refused_while_the_sentence_cannot_name_one() -> None:
    bpmn, dmn = _files()
    planted = bpmn.replace("<osprey:raise ", '<osprey:raise teamId="role-7" ', 1)
    with pytest.raises(UnsupportedElements) as refused:
        from_files(planted.encode(), dmn.encode())
    assert refused.value.names == ["osprey:teamId (on osprey:raise)"]


def test_the_files_rules_save_stores_are_the_codecs_own_bytes_and_import_back() -> None:
    rule = _rule()
    stored = rule_files(rule, dataset_id=DATASET)
    bpmn, dmn = _files(rule)
    assert (stored.bpmn, stored.dmn) == (bpmn.encode(), dmn.encode())
    assert from_files(stored.bpmn, stored.dmn) == RuleFile(rule=rule, dataset_id=DATASET)
