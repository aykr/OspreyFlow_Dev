"""The ask-to-search golden set's gate, shown red before it is trusted green (`CLAUDE.md` rule 15,
`06_DECISIONS.md` ADR-129 decision 2). Pure: no model is called, no service opened.

The measured run (`tests/golden/test_golden_ask_to_search.py`) needs a live model and is not in
`make ci`; what is in it is this file. It exists so that the gate's own comparison has been shown
able to fail, with a violation of the shape the code under test really receives: the fake model
answers in the wire shape the proposer's own JSON Schema allows (checked against that schema below,
so the fake cannot answer what the real decoder would refuse), and its answer goes through the real
`PatternProposer` and the real measuring loop (`run_pattern_cases`), exactly as a live model's does.

What a mistake in the gate would be, and the case that catches it (rule 12):

- a gate that passes whatever the model says (`test_a_planted_wrong_pattern_fails_the_gate`);
- a gate that is satisfied by refusing everything, or by never refusing
  (`test_refusing_everything_fails_the_gate`, `test_a_pattern_for_a_question_that_must_be_refused_
  scores_zero`);
- a golden set whose own expected pattern the ontology would refuse, which no model could ever
  match (`test_every_expected_pattern_passes_the_conduits_own_validation`);
- a baseline that has no recall yet being read as a pass
  (`test_a_baseline_with_no_recall_is_not_yet_measured_and_never_a_pass`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from services.api.pattern_ask import (
    PatternProposer,
    parse_proposal,
    proposal_schema,
    vocabulary_of,
)

from ontology.packs import load_deployment_ontology
from schemas.domain import PatternEdge, PatternNode, PatternQuery
from schemas.model import ExtractionRequest, ExtractionResult
from tests.golden.cases.pid_ask_to_search import CASE_ID, PID_ASK_TO_SEARCH_CASES
from tests.golden.harness import (
    PATTERN_CATEGORY,
    PatternGoldenCase,
    pattern_gate,
    run_pattern_cases,
    score_pattern,
    summarise_patterns,
)

ONTOLOGY = load_deployment_ontology()
VOCABULARY = vocabulary_of(ONTOLOGY)
UNDIRECTED = {e.name for e in ONTOLOGY.edge_types if not e.directed}
BASELINE = json.loads((Path(__file__).parent / "golden" / "baseline.json").read_text())

#: Brief 3's table, verbatim, so the cases cannot drift from what the owner asked.
BRIEF_QUESTIONS = (
    "Who shares a visitor with the principal?",
    "Which prisoners are paid from the same account as the principal?",
    "Which outside numbers are called by more than one prisoner's PIN account?",
    "Who has shared a cell with the principal?",
    "Who is in the same group as the principal?",
    "Which prisoners were found with a mobile phone since 1 January?",
    "Which prisoners are named in more than one report?",
    "Who are the principal's co-defendants?",
    "Which visitors have visited more than one prisoner?",
    "Who calls the coordinator's number?",
    "Who is in conflict with the principal?",
    "Which group members are on Wing F?",
    "Which prisoners were involved in an incident in one of the hotspot yards?",
    "Which reports name the principal?",
    "Which handsets are paired with a SIM that contacted the coordinator's number?",
    "Who is a relative of someone in a group?",
    "Who shares a visitor with the principal and is paid from the same account?",
    "Who is guilty?",
    "Who will throw the next package?",
    "Which prisoners have a phone I have not seen?",
)
ANSWERABLE = [c for c in PID_ASK_TO_SEARCH_CASES if c.expected is not None]
REFUSED = [c for c in PID_ASK_TO_SEARCH_CASES if c.expected is None]


def wire_of(pattern: PatternQuery) -> dict[str, Any]:
    """A pattern as a model's constrained answer carries it: the shape `proposal_schema` allows."""
    nodes: list[dict[str, Any]] = []
    for node in pattern.nodes:
        entry: dict[str, Any] = {"var": node.var, "entity_type": node.entity_type}
        if node.node_id:
            entry["reference"] = node.node_id
        if node.where:
            entry["where"] = [{"property": k, "value": v} for k, v in node.where.items()]
        nodes.append(entry)
    return {
        "can_express": True,
        "explanation": "Finds what was asked.",
        "nodes": nodes,
        "edges": [
            {"edge_type": e.edge_type, "from_var": e.from_var, "to_var": e.to_var}
            for e in pattern.edges
        ],
    }


DECLINES: dict[str, Any] = {"can_express": False, "explanation": "", "nodes": [], "edges": []}


class ScriptedModel:
    """A `ModelPort` that answers each question from a script, in the wire shape the schema it was
    sent allows. It refuses to answer what that schema would not let a real model write (rule 15:
    a fake models the real decoder's refusals, not only its grants)."""

    def __init__(self, answers: dict[str, dict[str, Any]], *, otherwise: dict[str, Any]) -> None:
        self.answers = answers
        self.otherwise = otherwise
        self.asked = 0

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.asked += 1
        question = req.text.rsplit("Question: ", 1)[1]
        data = self.answers.get(question, self.otherwise)
        jsonschema.validate(data, req.json_schema)
        return ExtractionResult(document_id=req.document_id, model=req.model, data=data)


def _proposer(model: ScriptedModel) -> PatternProposer:
    return PatternProposer(model, default_model="local-model")  # type: ignore[arg-type]


def _right_answers() -> dict[str, dict[str, Any]]:
    return {
        c.question: (DECLINES if c.expected is None else wire_of(c.expected))
        for c in PID_ASK_TO_SEARCH_CASES
    }


async def _measured_recall(model: ScriptedModel) -> float:
    scores = await run_pattern_cases(_proposer(model), PID_ASK_TO_SEARCH_CASES, ONTOLOGY, n_runs=2)
    return summarise_patterns(CASE_ID, scores)[CASE_ID][PATTERN_CATEGORY]["recall"]


#: A pattern the Conduit accepts and that is wrong for nearly every question: a person visited a
#: person. It is the shape the route really emits, not a hand-made score.
WRONG = PatternQuery(
    nodes=[PatternNode(var="a", entity_type="Person"), PatternNode(var="b", entity_type="Person")],
    edges=[PatternEdge(edge_type="VISITED", from_var="a", to_var="b")],
)


# --- the cases -------------------------------------------------------------------------------


def test_the_cases_are_the_briefs_twenty_questions_sixteen_to_answer_and_four_to_refuse() -> (
    None
):
    assert [c.question for c in PID_ASK_TO_SEARCH_CASES] == list(BRIEF_QUESTIONS)
    assert (len(ANSWERABLE), len(REFUSED)) == (16, 4)
    assert [c.question for c in REFUSED] == [BRIEF_QUESTIONS[5], *BRIEF_QUESTIONS[17:]]  # 6, 18-20
    assert len({c.id for c in PID_ASK_TO_SEARCH_CASES}) == 20


@pytest.mark.parametrize("case", ANSWERABLE, ids=lambda c: c.id)
def test_every_expected_pattern_passes_the_conduits_own_validation(case: PatternGoldenCase) -> None:
    """A golden pattern the ontology would refuse could never be matched by any model, and the gate
    would measure the pattern, not the model. Each goes through the proposer's own `parse_proposal`,
    with only the placeholders the case offers, and comes back as written."""
    assert case.expected is not None
    wire = wire_of(case.expected)
    jsonschema.validate(wire, proposal_schema(VOCABULARY, case.selected))
    parsed, _ = parse_proposal(wire, VOCABULARY, ONTOLOGY, case.selected)
    assert parsed == case.expected


@pytest.mark.parametrize("case", ANSWERABLE, ids=lambda c: c.id)
def test_a_question_about_the_principal_offers_a_placeholder_and_one_that_is_not_does_not(
    case: PatternGoldenCase,
) -> None:
    assert case.expected is not None
    pinned = [n for n in case.expected.nodes if n.node_id]
    assert bool(case.selected) == bool(pinned)
    assert all(n.node_id == "$selected_1" for n in pinned)


# --- the scorer ------------------------------------------------------------------------------


def _pattern(link: str = "VISITED", ends: tuple[str, str] = ("Person", "Person")) -> PatternQuery:
    return PatternQuery(
        nodes=[
            PatternNode(var="a", entity_type=ends[0]),
            PatternNode(var="b", entity_type=ends[1]),
        ],
        edges=[PatternEdge(edge_type=link, from_var="a", to_var="b")],
    )


def test_a_pattern_equal_to_the_expected_one_scores_one_whatever_its_variables_are_called() -> None:
    renamed = PatternQuery(
        nodes=[
            PatternNode(var="x", entity_type="Person"),
            PatternNode(var="y", entity_type="Person"),
        ],
        edges=[PatternEdge(edge_type="VISITED", from_var="x", to_var="y")],
    )
    assert score_pattern(_pattern(), renamed) == score_pattern(_pattern(), _pattern())
    assert (
        score_pattern(_pattern(), renamed).recall,
        score_pattern(_pattern(), renamed).precision,
    ) == (1.0, 1.0)


def test_a_missing_part_lowers_recall_and_an_extra_part_lowers_precision() -> None:
    wanted = PatternQuery(
        nodes=[
            PatternNode(var="a", entity_type="Person"),
            PatternNode(var="b", entity_type="Person", where={"family_name": "Shah"}),
        ],
        edges=[PatternEdge(edge_type="VISITED", from_var="a", to_var="b")],
    )
    without_condition = _pattern()
    missing = score_pattern(wanted, without_condition)
    assert missing.recall < 1.0 and missing.precision == 1.0
    extra = score_pattern(without_condition, wanted)
    assert extra.recall == 1.0 and extra.precision < 1.0


def test_a_directed_link_run_the_wrong_way_is_a_miss_and_an_undirected_one_is_not() -> None:
    forward = _pattern("VISITED", ("Person", "Organisation"))
    backward = PatternQuery(
        nodes=forward.nodes, edges=[PatternEdge(edge_type="VISITED", from_var="b", to_var="a")]
    )
    assert score_pattern(forward, backward).recall < 1.0
    assert "SHARED_CELL_WITH" in UNDIRECTED
    shared = _pattern("SHARED_CELL_WITH", ("Person", "Organisation"))
    shared_back = PatternQuery(
        nodes=shared.nodes,
        edges=[PatternEdge(edge_type="SHARED_CELL_WITH", from_var="b", to_var="a")],
    )
    assert score_pattern(shared, shared_back, undirected=UNDIRECTED).recall == 1.0
    assert score_pattern(shared, shared_back).recall < 1.0


def test_two_different_documents_need_two_not_one() -> None:
    case = next(c for c in ANSWERABLE if c.question.endswith("more than one report?"))
    assert case.expected is not None
    one_document = PatternQuery(
        nodes=case.expected.nodes[:2],
        edges=case.expected.edges[:1],
    )
    assert score_pattern(case.expected, one_document).recall < 1.0


def test_a_refusal_is_correct_only_when_refused() -> None:
    assert score_pattern(None, None).recall == 1.0
    assert score_pattern(None, _pattern()).recall == 0.0
    assert score_pattern(None, _pattern()).precision == 0.0
    assert score_pattern(_pattern(), None).recall == 0.0


# --- the gate, shown green and then red (rule 15) --------------------------------------------


async def test_the_right_pattern_for_every_question_scores_one_and_passes_the_gate() -> None:
    model = ScriptedModel(_right_answers(), otherwise=DECLINES)
    recall = await _measured_recall(model)
    assert recall == 1.0
    assert pattern_gate(CASE_ID, recall, {CASE_ID: {PATTERN_CATEGORY: {"recall": 0.9}}}).status == (
        "passed"
    )


async def test_a_planted_wrong_pattern_fails_the_gate() -> None:
    """The planted violation: for every answerable question the model proposes `WRONG`, a pattern
    the Conduit accepts (it goes through the real proposer), and refuses the four it should. The
    gate, over a baseline of 0.9, must be red."""
    answers = {c.question: wire_of(WRONG) for c in ANSWERABLE}
    model = ScriptedModel(answers, otherwise=DECLINES)
    recall = await _measured_recall(model)
    assert recall < 0.75
    result = pattern_gate(CASE_ID, recall, {CASE_ID: {PATTERN_CATEGORY: {"recall": 0.9}}})
    assert result.status == "failed"
    assert "below floor" in result.message


async def test_refusing_everything_fails_the_gate() -> None:
    recall = await _measured_recall(ScriptedModel({}, otherwise=DECLINES))
    assert recall == pytest.approx(4 / 20)
    result = pattern_gate(CASE_ID, recall, {CASE_ID: {PATTERN_CATEGORY: {"recall": 0.9}}})
    assert result.status == "failed"


async def test_a_pattern_for_a_question_that_must_be_refused_scores_zero() -> None:
    """The four refusals are in the mean: a model that answers them all loses 4 of 20."""
    answers = _right_answers()
    for case in REFUSED:
        answers[case.question] = wire_of(WRONG)
    recall = await _measured_recall(ScriptedModel(answers, otherwise=DECLINES))
    assert recall == pytest.approx(16 / 20)


async def test_the_measuring_loop_asks_every_question_every_run() -> None:
    model = ScriptedModel(_right_answers(), otherwise=DECLINES)
    scores = await run_pattern_cases(_proposer(model), PID_ASK_TO_SEARCH_CASES, ONTOLOGY, n_runs=3)
    assert model.asked == 60
    assert {len(runs) for runs in scores.values()} == {3}


def test_the_floor_is_the_baseline_less_the_tolerance_and_the_edge_is_inclusive() -> None:
    baseline = {CASE_ID: {PATTERN_CATEGORY: {"recall": 0.75}}}  # floor 0.5, exact in binary
    assert pattern_gate(CASE_ID, 0.49, baseline, tolerance=0.25).status == "failed"
    assert pattern_gate(CASE_ID, 0.5, baseline, tolerance=0.25).status == "passed"
    assert pattern_gate(CASE_ID, 0.99, baseline, tolerance=0.25).status == "passed"


def test_a_baseline_with_no_recall_is_not_yet_measured_and_never_a_pass() -> None:
    entry = BASELINE[CASE_ID][PATTERN_CATEGORY]
    assert set(entry) == {"precision", "recall"}  # the placeholder until the first measured run
    if entry["recall"] is None:
        result = pattern_gate(CASE_ID, 1.0, BASELINE)
        assert result.status == "not_yet_measured"
        assert "no recall yet" in result.message
    assert pattern_gate(CASE_ID, 1.0, {}).status == "not_yet_measured"
