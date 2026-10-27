"""Ask to search (`06_DECISIONS.md` ADR-129 decision 2, Brief 3 item E3): the model is given the
case's vocabulary and a question, and proposes a pattern that nothing runs.

These tests run the real `WorkingSetService` projection over a fake store and a model that records
exactly what it was sent, so the access cases compare the bytes of two prompts, as
`test_questions_graph_facts.py` does.

What a mistake here would do, and the case that catches it (rule 12):

- a type, link, property or value the ontology does not hold would be drawn as a pattern: each is
  refused (`test_a_proposal_the_ontology_refuses_is_could_not_express`), by a model answering what
  constrained decoding would not let it, since a fake is not constrained (rule 15: the real one
  refuses these at the decoder, and the Conduit is the second line);
- `$selected_1` would resolve to a node the analyst may not see: a hidden id and a made-up id give
  the same refusal and the same prompt, and a cleared reader's own id resolves, so the comparison
  is able to fail (`test_a_placeholder_never_resolves_to_a_node_the_analyst_cannot_see`);
- an id would reach the model (`test_the_model_sees_no_id`);
- the count would come from somewhere other than the preview's own path, or something would run
  (`test_the_count_comes_from_the_existing_preview_path_and_nothing_runs`).

Where this file cannot prove it: that a 7B model proposes the right pattern (the golden set measures
it, `tests/golden/cases/pid_ask_to_search.py`), and that the store counts as the reader (the
conformance suite's, since the fake graph here counts nothing).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import pattern_ask, patterns
from services.api.app import (
    app,
    get_audit,
    get_graph,
    get_investigations,
    get_ontology,
    get_pattern_ask,
    get_principal,
)
from services.api.pattern_ask import (
    CouldNotExpress,
    PatternAskService,
    vocabulary_of,
)
from services.api.patterns import PREVIEW_COUNT_CEILING
from services.api.working_set.service import WorkingSetService

from ontology.packs import load_deployment_ontology
from schemas.domain import (
    EdgeTypeDef,
    EntityTypeDef,
    OntologySchema,
    PatternQuery,
    PoleClass,
    Principal,
    PropertyDef,
    PropertyType,
    Subgraph,
)
from schemas.model import ExtractionRequest, ExtractionResult
from tests.services.api.any_case import AnyCase

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, node

ONTOLOGY = load_deployment_ontology()
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
CLEARED = Principal(id="analyst-3", clearance="SECRET", org_unit="unit-1", roles=["analyst"])

DANA, CALLUM = "node-dana-7f3a", "node-callum-9c1b"
HIDDEN = "node-hidden-b7c2"
MADE_UP = "node-never-existed-0d44"
BASE = "/v1/investigations/inv-1/patterns/ask"


def _wire(
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
    *,
    can_express: bool = True,
    explanation: str = "Finds people who visited two others.",
) -> dict[str, Any]:
    """The model's answer, in the shape the schema it was sent makes it."""
    return {
        "can_express": can_express,
        "explanation": explanation,
        "nodes": nodes if nodes is not None else [],
        "edges": edges if edges is not None else [],
    }


def _two_visited(reference: str | None = None) -> dict[str, Any]:
    """A visitor who visited two people, one of them the selected person when `reference` is set."""
    second: dict[str, Any] = {"var": "b", "entity_type": "Person"}
    if reference is not None:
        second["reference"] = reference
    return _wire(
        [{"var": "a", "entity_type": "Person"}, second, {"var": "c", "entity_type": "Person"}],
        [
            {"edge_type": "VISITED", "from_var": "a", "to_var": "b"},
            {"edge_type": "VISITED", "from_var": "a", "to_var": "c"},
        ],
    )


class RecordingModel:
    """A `ModelPort` that answers one fixed thing and keeps every request it was sent."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.requests: list[ExtractionRequest] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.requests.append(req)
        return ExtractionResult(document_id=req.document_id, model=req.model, data=self.data)


class CountingGraph:
    """Counts as the preview asks, and refuses to run: ask to search never calls `match`."""

    def __init__(self, count: int = 0, *, refuses: str | None = None) -> None:
        self.count = count
        self.refuses = refuses
        self.counted: list[tuple[PatternQuery, Principal, int]] = []
        self.matched = 0

    async def match_count(
        self, pattern: PatternQuery, principal: Principal, *, ceiling: int
    ) -> int:
        if self.refuses is not None:
            raise ValueError(self.refuses)
        self.counted.append((pattern, principal, ceiling))
        return self.count

    async def match(self, pattern: PatternQuery, principal: Principal) -> Any:
        self.matched += 1
        raise AssertionError("ask to search must not run a pattern")


async def _case(
    data: dict[str, Any], *, count: int = 0, refuses: str | None = None
) -> tuple[PatternAskService, RecordingModel, CountingGraph]:
    store = FakeWorkingSetStore()
    await store.add_nodes(
        "inv-1",
        [node(DANA), node(CALLUM), node(HIDDEN, "SECRET")],
    )
    graph = CountingGraph(count, refuses=refuses)
    model = RecordingModel(data)
    working_set = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)
    service = PatternAskService(
        working_set,
        graph,
        model,  # type: ignore[arg-type]
        default_model="local-model",
    )
    return service, model, graph


async def _ask(
    service: PatternAskService,
    principal: Principal = ANALYST,
    selected: list[str] | None = None,
    question: str = "Who shares a visitor with the principal?",
) -> pattern_ask.PatternProposal:
    return await service.ask(
        "inv-1",
        pattern_ask.AskToSearchRequest(question=question, selected_node_ids=selected or []),
        principal,
        ONTOLOGY,
    )


# --- the proposal is validated against the ontology and the pattern rules ---------------------


async def test_a_proposal_over_the_vocabulary_is_returned_with_its_explanation_and_count() -> None:
    service, _, graph = await _case(_two_visited(), count=7)
    proposal = await _ask(service)
    assert [n.entity_type for n in proposal.pattern.nodes] == ["Person"] * 3
    assert [(e.edge_type, e.from_var, e.to_var) for e in proposal.pattern.edges] == [
        ("VISITED", "a", "b"),
        ("VISITED", "a", "c"),
    ]
    assert proposal.explanation == "Finds people who visited two others."
    assert (proposal.estimated_count, proposal.is_floor) == (7, False)
    assert graph.matched == 0


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        pytest.param(
            _wire([{"var": "a", "entity_type": "Spaceship"}]), "unknown_type", id="unknown-type"
        ),
        pytest.param(
            _wire(
                [{"var": "a", "entity_type": "Person"}, {"var": "b", "entity_type": "Person"}],
                [{"edge_type": "ORBITS", "from_var": "a", "to_var": "b"}],
            ),
            "unknown_link",
            id="unknown-link",
        ),
        pytest.param(
            _wire(
                [{"var": "a", "entity_type": "Person"}, {"var": "b", "entity_type": "Document"}],
                [{"edge_type": "VISITED", "from_var": "a", "to_var": "b"}],
            ),
            "link_ends",
            id="a-link-between-types-it-does-not-join",
        ),
        pytest.param(
            _wire(
                [{"var": "a", "entity_type": "Person"}],
                [{"edge_type": "VISITED", "from_var": "a", "to_var": "z"}],
            ),
            "unknown_variable",
            id="a-link-to-a-variable-nobody-declared",
        ),
        pytest.param(
            _wire([{"var": "a", "entity_type": "Person"}, {"var": "a", "entity_type": "Person"}]),
            "repeated_variable",
            id="a-variable-declared-twice",
        ),
        pytest.param(
            _wire(
                [
                    {
                        "var": "a",
                        "entity_type": "Person",
                        "where": [{"property": "shoe_size", "value": "9"}],
                    }
                ]
            ),
            "condition_refused",
            id="unknown-property",
        ),
        pytest.param(
            _wire(
                [
                    {
                        "var": "a",
                        "entity_type": "Person",
                        "where": [{"property": "date_of_birth", "value": "1990-01-01"}],
                    }
                ]
            ),
            "condition_refused",
            id="a-sensitive-property",
        ),
        pytest.param(
            _wire(
                [
                    {
                        "var": "a",
                        "entity_type": "Incident",
                        "where": [{"property": "category", "value": "find"}],
                    }
                ]
            ),
            "condition_refused",
            id="a-property-that-is-not-indexed",
        ),
        pytest.param(
            _wire(
                [
                    {
                        "var": "a",
                        "entity_type": "Person",
                        "where": [
                            {"property": "family_name", "value": "Shah"},
                            {"property": "family_name", "value": "Okoye"},
                        ],
                    }
                ]
            ),
            "malformed",
            id="one-property-twice",
        ),
        pytest.param(
            _wire(
                [
                    {
                        "var": "a",
                        "entity_type": "Person",
                        "where": [{"property": "family_name", "value": ""}],
                    }
                ]
            ),
            "malformed",
            id="an-empty-value",
        ),
        pytest.param(
            _wire([{"var": "a", "entity_type": "Person"}], can_express=False),
            "model_declined",
            id="model-declines",
        ),
        pytest.param(_wire([]), "no_pattern", id="no-nodes-at-all"),
        pytest.param({"can_express": True}, "malformed", id="no-nodes-field"),
        pytest.param(
            _wire([{"var": "a", "entity_type": "Person", "reference": "$selected_1"}]),
            "unresolved_reference",
            id="a-placeholder-with-nothing-selected",
        ),
        pytest.param(
            _wire([{"var": "a", "entity_type": "Person", "node_id": DANA}]),
            "malformed",
            id="a-node-id-the-model-was-never-given",
        ),
    ],
)
async def test_a_proposal_the_ontology_refuses_is_could_not_express(
    data: dict[str, Any], reason: str
) -> None:
    service, _, graph = await _case(data)
    with pytest.raises(CouldNotExpress) as refused:
        await _ask(service)
    assert refused.value.reason == reason
    assert graph.counted == []  # refused before anything is counted
    assert graph.matched == 0


async def test_a_pattern_the_builder_cannot_run_is_could_not_express_not_a_server_error() -> None:
    service, _, _ = await _case(
        _wire([{"var": "a", "entity_type": "Person"}, {"var": "b", "entity_type": "Person"}]),
        refuses="an open second root has no general join on this adapter",
    )
    with pytest.raises(CouldNotExpress) as refused:
        await _ask(service)
    assert refused.value.reason == "not_runnable"


async def test_the_explanation_is_one_line_and_a_missing_one_is_written_from_the_pattern() -> None:
    service, _, _ = await _case(
        _wire([{"var": "a", "entity_type": "Person"}], explanation="First line.\nSecond   line.")
    )
    assert (await _ask(service)).explanation == "First line. Second line."

    blank, _, _ = await _case(_wire([{"var": "a", "entity_type": "Person"}], explanation="  "))
    assert (await _ask(blank)).explanation == "Finds a: Person."


# --- placeholders ----------------------------------------------------------------------------


async def test_a_placeholder_resolves_to_the_selection_in_the_pattern_and_is_counted() -> None:
    service, _, graph = await _case(_two_visited("$selected_2"), count=3)
    proposal = await _ask(service, selected=[CALLUM, DANA])
    assert [n.node_id for n in proposal.pattern.nodes] == [None, DANA, None]
    ((counted, principal, _),) = graph.counted
    assert counted == proposal.pattern and principal == ANALYST


@pytest.mark.parametrize(
    "selection",
    [[HIDDEN], [MADE_UP], [HIDDEN, MADE_UP], []],
    ids=["hidden", "made-up", "both", "nothing"],
)
async def test_a_placeholder_never_resolves_to_a_node_the_analyst_cannot_see(
    selection: list[str],
) -> None:
    """Rule 3. A hidden id, a made-up one and no selection at all are the same to the analyst:
    the same refusal, the same words, and the same prompt, so no response tells them apart."""
    service, model, graph = await _case(_two_visited("$selected_1"))
    with pytest.raises(CouldNotExpress) as refused:
        await _ask(service, selected=selection)
    nothing, nothing_model, _ = await _case(_two_visited("$selected_1"))
    with pytest.raises(CouldNotExpress) as baseline:
        await _ask(nothing)
    assert (refused.value.reason, refused.value.detail) == (
        baseline.value.reason,
        baseline.value.detail,
    )
    assert refused.value.reason == "unresolved_reference"
    assert model.requests[0].text == nothing_model.requests[0].text
    assert graph.counted == []


async def test_the_cleared_reader_is_given_the_hidden_node_so_the_comparison_can_fail() -> None:
    service, model, graph = await _case(_two_visited("$selected_1"))
    proposal = await _ask(service, CLEARED, selected=[HIDDEN])
    assert proposal.pattern.nodes[1].node_id == HIDDEN
    assert "$selected_1" in model.requests[0].text
    assert graph.counted[0][1] == CLEARED


async def test_a_hidden_id_beside_a_visible_one_leaves_the_visible_one_first() -> None:
    """The prompt and the pattern are what they would be for the visible one alone."""
    service, model, graph = await _case(_two_visited("$selected_1"))
    both = await _ask(service, selected=[HIDDEN, DANA])
    alone_service, alone_model, _ = await _case(_two_visited("$selected_1"))
    alone = await _ask(alone_service, selected=[DANA])
    assert both.pattern == alone.pattern
    assert both.pattern.nodes[1].node_id == DANA
    assert model.requests[0].text == alone_model.requests[0].text
    assert "selected_2" not in model.requests[0].text


async def test_a_placeholder_past_the_selection_is_unresolved() -> None:
    service, _, _ = await _case(_two_visited("$selected_2"))
    with pytest.raises(CouldNotExpress) as refused:
        await _ask(service, selected=[DANA])
    assert refused.value.reason == "unresolved_reference"


# --- what the model is sent ------------------------------------------------------------------


async def test_the_model_sees_no_id() -> None:
    service, model, _ = await _case(_two_visited("$selected_1"))
    await _ask(service, CLEARED, selected=[HIDDEN, DANA, MADE_UP])
    (request,) = model.requests
    sent = request.model_dump_json()
    for secret in (DANA, CALLUM, HIDDEN, MADE_UP):
        assert secret not in sent
    assert request.handling is None
    assert request.model == "local-model"
    assert "Who shares a visitor with the principal?" in request.text
    # What it is told instead: how many placeholders there are, and nothing about what they are.
    assert "$selected_1" in request.text and "$selected_2" in request.text
    assert "$selected_3" not in request.text


async def test_the_model_is_sent_the_vocabulary_and_a_schema_that_only_allows_it() -> None:
    service, model, _ = await _case(_two_visited())
    await _ask(service)
    (request,) = model.requests
    for named in ("Person", "VISITED", "Incident", "family_name"):
        assert named in request.text
    schema = request.json_schema
    node_schema = schema["properties"]["nodes"]["items"]["properties"]
    link_schema = schema["properties"]["edges"]["items"]["properties"]
    assert set(node_schema["entity_type"]["enum"]) == {t.name for t in ONTOLOGY.entity_types}
    assert "VISITED" in link_schema["edge_type"]["enum"]
    assert "SAME_AS" not in link_schema["edge_type"]["enum"]  # a system link is not offered
    assert "reference" not in node_schema  # nothing selected, so nothing to refer to
    assert "node_id" not in node_schema  # an id is never the model's to write
    assert json.dumps(schema)  # a JSON Schema the decoder can take


async def test_the_schema_offers_a_placeholder_only_for_what_is_selected() -> None:
    service, model, _ = await _case(_two_visited())
    await _ask(service, selected=[DANA, CALLUM, HIDDEN])
    reference = model.requests[0].json_schema["properties"]["nodes"]["items"]["properties"][
        "reference"
    ]
    assert reference["enum"] == ["$selected_1", "$selected_2"]


# --- the vocabulary --------------------------------------------------------------------------


def _small_ontology() -> OntologySchema:
    def entity(name: str, props: list[PropertyDef]) -> EntityTypeDef:
        return EntityTypeDef(
            name=name, pole_class=PoleClass.OBJECT, channel="indigo", shape="circle",
            properties=props,
        )  # fmt: skip

    return OntologySchema(
        version=1,
        entity_types=[
            entity(
                "Thing",
                [
                    PropertyDef(name="label", type=PropertyType.STRING, indexed=True),
                    PropertyDef(
                        name="grade", type=PropertyType.ENUM, indexed=True, values=["low", "high"]
                    ),
                    PropertyDef(
                        name="secret", type=PropertyType.STRING, indexed=True, sensitivity="high"
                    ),
                    PropertyDef(name="loose", type=PropertyType.STRING),
                    PropertyDef(name="count", type=PropertyType.INTEGER, indexed=True),
                ],
            ),
            entity("Other", []),
        ],
        edge_types=[
            EdgeTypeDef(name="TOUCHES", **{"from": ["Thing"], "to": ["Other"]}, directed=True),
            EdgeTypeDef(name="NEAR", **{"from": ["Thing"], "to": ["Thing"]}, directed=False),
            EdgeTypeDef(name="SAME_AS", **{"from": ["*"], "to": ["*"]}, system=True),
            EdgeTypeDef(name="PROPOSED", **{"from": ["Thing"], "to": ["Other"]}, hidden=True),
        ],
    )


def test_the_vocabulary_is_the_indexed_text_properties_and_the_links_an_analyst_may_draw() -> None:
    vocabulary = vocabulary_of(_small_ontology())
    assert vocabulary.entity_types == ("Thing", "Other")
    assert [(link.name, link.directed) for link in vocabulary.links] == [
        ("TOUCHES", True),
        ("NEAR", False),
    ]
    assert [(p.entity_type, p.name, p.values) for p in vocabulary.properties] == [
        ("Thing", "label", None),
        ("Thing", "grade", ("low", "high")),
    ]
    text = vocabulary.text()
    for named in ("Thing", "TOUCHES", "NEAR", "label", "grade", "low", "high"):
        assert named in text
    for left_out in ("secret", "loose", "count", "SAME_AS", "PROPOSED"):
        assert left_out not in text


# --- the route -------------------------------------------------------------------------------


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


@pytest.fixture
def client() -> Iterator[TestClient]:
    state: dict[str, Any] = {"audit": _Audit()}
    app.dependency_overrides[get_principal] = lambda: ANALYST
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: state["audit"]
    app.dependency_overrides[get_ontology] = lambda: ONTOLOGY
    app.dependency_overrides[get_graph] = lambda: state["graph"]
    app.dependency_overrides[get_pattern_ask] = lambda: state["service"]
    test_client = TestClient(app)
    test_client.state = state  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


async def _route_case(client: TestClient, data: dict[str, Any], count: int = 4) -> CountingGraph:
    service, _, graph = await _case(data, count=count)
    client.state.update(service=service, graph=graph)  # type: ignore[attr-defined]
    return graph


async def test_the_route_answers_the_pattern_the_explanation_and_the_count(
    client: TestClient,
) -> None:
    graph = await _route_case(client, _two_visited("$selected_1"))
    response = client.post(
        BASE,
        json={"question": "Who shares a visitor with the principal?", "selected_node_ids": [DANA]},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"pattern", "explanation", "estimated_count", "is_floor"}
    assert body["estimated_count"] == 4 and body["is_floor"] is False
    assert body["pattern"]["nodes"][1]["node_id"] == DANA
    assert graph.matched == 0
    (record,) = client.state["audit"].records  # type: ignore[attr-defined]
    assert record["action"] == "patterns_ask"


async def test_the_route_refuses_in_a_typed_422_and_a_hidden_id_reads_as_a_made_up_one(
    client: TestClient,
) -> None:
    await _route_case(client, _two_visited("$selected_1"))
    hidden = client.post(BASE, json={"question": "Who is it?", "selected_node_ids": [HIDDEN]})
    made_up = client.post(BASE, json={"question": "Who is it?", "selected_node_ids": [MADE_UP]})
    assert hidden.status_code == made_up.status_code == 422
    assert hidden.json() == made_up.json()
    assert hidden.json()["error"] == "could_not_express"
    assert hidden.json()["reason"] == "unresolved_reference"
    assert HIDDEN not in hidden.text


async def test_the_route_refuses_an_unknown_type_in_a_typed_422(client: TestClient) -> None:
    graph = await _route_case(client, _wire([{"var": "a", "entity_type": "Spaceship"}]))
    response = client.post(BASE, json={"question": "Which spaceships are there?"})
    assert response.status_code == 422
    assert response.json()["error"] == "could_not_express"
    assert response.json()["reason"] == "unknown_type"
    assert graph.counted == []


@pytest.mark.parametrize(
    "body",
    [{"question": ""}, {"question": "   "}, {"question": "x" * 1001}, {}],
    ids=["empty", "blank", "too-long", "absent"],
)
async def test_the_route_refuses_a_question_it_cannot_ask(
    client: TestClient, body: dict[str, Any]
) -> None:
    await _route_case(client, _two_visited())
    assert client.post(BASE, json=body).status_code == 422


# --- the count and nothing running -----------------------------------------------------------


async def test_the_count_comes_from_the_existing_preview_path_and_nothing_runs() -> None:
    assert pattern_ask.preview_pattern is patterns.preview_pattern
    service, _, graph = await _case(_two_visited(), count=PREVIEW_COUNT_CEILING)
    proposal = await _ask(service)
    # The same call the preview route makes: the port's own count, to the preview's own ceiling,
    # as the reader. Nothing was matched, queued or stored.
    ((_, principal, ceiling),) = graph.counted
    assert (principal, ceiling) == (ANALYST, PREVIEW_COUNT_CEILING)
    assert proposal.estimated_count == PREVIEW_COUNT_CEILING and proposal.is_floor is True
    assert graph.matched == 0
