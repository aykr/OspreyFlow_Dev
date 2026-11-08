"""Expert mode at the Studio's routes (ADR-140 decisions 3, 12, 13 and 16; the redesign's phase 8).
What a mistake would do, and the case that catches it:

- an expert step saved by someone without `write_sql_transforms`, through the canvas or the YAML
  (`test_an_expert_step_is_saved_only_with_the_right`, `test_the_yaml_save_has_the_same_gates`),
  or a pipeline holding one locked against everyone else's edits (`test_…other_steps…without_it`);
- the YAML being run rather than read (`test_the_yaml_is_read_never_run`), or refused in other
  words than the canvas's gate (`test_the_yaml_save_has_the_same_gates`);
- Check SQL open to anyone (`test_check_sql_needs_the_right`) or saying other than the gate
  (`test_check_sql_says_what_the_gate_says`);
- a step's drawer sample or Test of an expert step giving an uncleared reader anything (rule 3:
  `test_an_expert_step_s_sample_and_test_give_an_uncleared_reader_nothing`);
- Test not disclosing the expert steps (`test_test_discloses_both_expert_steps`);
- the threshold left out of what is deployed (`test_the_threshold_is_deployed_with_the_version`;
  two thresholds as two versions with two counts: `tests/ingest/test_fuzzy_match.py`).
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from services.api.app import app, get_principal, get_staging_storage, get_target_models
from services.ingest.pipeline import pipeline_with_staging
from services.ingest.recipe_loader import load_recipe

from schemas.ingest import PipelineEdge, PipelineGraph, PipelineNode, PipelineNodeKind
from tests.services.api.test_studio_publish_routes import git_repo  # noqa: F401  (a fixture)
from tests.services.api.test_studio_recipe_routes import (
    _UNCLEARED_HANDLING,
    SOURCE_APPROVER,
    SOURCE_AUTHOR,
    _ready_draft,
)
from tests.services.api.test_studio_staging_routes import STORAGE, _Models, store  # noqa: F401
from tests.services.api.test_studio_verify_routes import (  # noqa: F401  (fixtures)
    client,
    graph_client,
)
from tests.ingest.test_staged_run import ESTABLISHMENTS

# ruff: noqa: F811  (the imported fixtures are every test's own same-named parameters)

RECIPE_URL = "/v1/investigations/inv-1/ingest/recipes/recipe-1"
FIXTURES = Path(__file__).parents[2] / "ingest" / "fixtures" / "visits_contacts_calls"
RECIPE = load_recipe(FIXTURES / "visits_contacts_calls_recipe.yaml")
WRITER = SOURCE_AUTHOR.model_copy(
    update={"roles": ["source_author", "right:write_sql_transforms"], "datasets": ["pid"]}
)
EDITOR = SOURCE_AUTHOR.model_copy(update={"datasets": ["pid"]})


def _pipeline(tmp_path: Path, staging: Any = None) -> PipelineGraph:
    nodes = [PipelineNode(id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model")]
    edges = []
    for name in ("visit_bookings", "number_owners", "pin_calls"):
        located = tmp_path / f"{name}.csv"
        shutil.copy(FIXTURES / f"{name}.csv", located)
        config = {} if name == "visit_bookings" else {"source_location": str(located)}
        nodes.append(PipelineNode(id=name, kind=PipelineNodeKind.SOURCE, label=name, config=config))
        edges.append(PipelineEdge(source="domain", target=name))
    nodes += [
        PipelineNode(id="map", kind=PipelineNodeKind.MAP, label="Map"),
        PipelineNode(id="load", kind=PipelineNodeKind.LOAD, label="Load"),
    ]
    edges.append(PipelineEdge(source="map", target="load"))
    return pipeline_with_staging(
        PipelineGraph(nodes=nodes, edges=edges), staging if staging is not None else RECIPE.staging
    )


@pytest.fixture
def expert(graph_client: TestClient, tmp_path: Path, store: Path) -> TestClient:
    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path,
        source_location=str(tmp_path / "visit_bookings.csv"),
        dataset_id="pid",
        row_template=RECIPE.row_template,
        pipeline=_pipeline(tmp_path),
    )
    app.dependency_overrides[get_principal] = lambda: WRITER
    app.dependency_overrides[get_target_models] = lambda: _Models([ESTABLISHMENTS.id])
    app.dependency_overrides[get_staging_storage] = lambda: STORAGE
    return graph_client


def _draft(client: TestClient) -> Any:
    return client.studio_recipes.draft  # type: ignore[attr-defined]


def _without_expert_steps(tmp_path: Path) -> PipelineGraph:
    assert RECIPE.staging
    return _pipeline(tmp_path, [s for s in RECIPE.staging if s.kind not in ("sql", "fuzzy_match")])


def _sql_node(graph: PipelineGraph) -> PipelineNode:
    return next(n for n in graph.nodes if n.kind is PipelineNodeKind.SQL)


def test_an_expert_step_is_saved_only_with_the_right(expert: TestClient, tmp_path: Path) -> None:
    """ADR-140 decision 3. Red with the check removed: the editor's save stores the SQL step."""
    full = _draft(expert).pipeline
    _draft(expert).pipeline = _without_expert_steps(tmp_path)
    before = _draft(expert).pipeline
    app.dependency_overrides[get_principal] = lambda: EDITOR
    refused = expert.put(f"{RECIPE_URL}/pipeline", json=full.model_dump(mode="json"))
    assert refused.status_code == 403, refused.text
    assert refused.json()["right"] == "write_sql_transforms"
    assert any("expert step" in p for p in refused.json()["problems"])
    assert _draft(expert).pipeline == before
    app.dependency_overrides[get_principal] = lambda: WRITER
    saved = expert.put(f"{RECIPE_URL}/pipeline", json=full.model_dump(mode="json"))
    assert saved.status_code == 200, saved.text


@pytest.mark.parametrize("change", ["edit", "remove"])
def test_changing_or_removing_an_expert_step_needs_the_right(
    expert: TestClient, tmp_path: Path, change: str
) -> None:
    graph = _draft(expert).pipeline.model_copy(deep=True)
    if change == "edit":
        _sql_node(graph).config["select"] = _sql_node(graph).config["select"] + " LIMIT 2"
    else:
        graph = _without_expert_steps(tmp_path)
    app.dependency_overrides[get_principal] = lambda: EDITOR
    assert expert.put(f"{RECIPE_URL}/pipeline", json=graph.model_dump(mode="json")).status_code == 403


def test_the_pipeline_s_other_steps_are_edited_without_it(expert: TestClient) -> None:
    graph = _draft(expert).pipeline.model_copy(deep=True)
    titled = next(n for n in graph.nodes if n.id == "titled")
    titled.config["settings"] = {"separator": " / "}
    app.dependency_overrides[get_principal] = lambda: EDITOR
    response = expert.put(f"{RECIPE_URL}/pipeline", json=graph.model_dump(mode="json"))
    assert response.status_code == 200, response.text


def test_the_yaml_round_trips(expert: TestClient) -> None:
    shown = expert.get(f"{RECIPE_URL}/pipeline/yaml")
    assert shown.status_code == 200
    text = shown.json()["text"]
    assert "fuzzy_match" in text and "SELECT t.* EXCLUDE (title)" in text
    saved = expert.put(f"{RECIPE_URL}/pipeline/yaml", json={"text": text})
    assert saved.status_code == 200, saved.text
    assert _draft(expert).pipeline == PipelineGraph.model_validate(yaml.safe_load(text))


def test_the_yaml_save_has_the_same_gates(expert: TestClient) -> None:
    data = yaml.safe_load(expert.get(f"{RECIPE_URL}/pipeline/yaml").json()["text"])
    sql = next(n for n in data["nodes"] if n["kind"] == "sql")
    sql["config"]["select"] = "SELECT * FROM read_csv('/etc/passwd')"
    text = yaml.safe_dump(data, sort_keys=False)
    as_yaml = expert.put(f"{RECIPE_URL}/pipeline/yaml", json={"text": text})
    as_graph = expert.put(f"{RECIPE_URL}/pipeline", json=data)
    assert as_yaml.status_code == as_graph.status_code == 422
    assert as_yaml.json()["problems"] == as_graph.json()["problems"]
    assert any("table function (read_csv)" in p for p in as_yaml.json()["problems"])
    app.dependency_overrides[get_principal] = lambda: EDITOR
    refused = expert.put(f"{RECIPE_URL}/pipeline/yaml", json={"text": text})
    assert refused.status_code == 403 and refused.json()["right"] == "write_sql_transforms"


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("nodes: [", "cannot be read"),
        ("- just a list", "is not a pipeline"),
        ("!!python/object/apply:os.system ['true']", "cannot be read"),
        ("nodes: [{id: x}]", "nodes.0.kind"),
    ],
)
def test_the_yaml_is_read_never_run(expert: TestClient, text: str, words: str) -> None:
    before = _draft(expert).pipeline
    response = expert.put(f"{RECIPE_URL}/pipeline/yaml", json={"text": text})
    assert response.status_code == 422, response.text
    assert any(words in p for p in response.json()["problems"]), response.json()
    assert _draft(expert).pipeline == before


def test_check_sql_needs_the_right(expert: TestClient) -> None:
    body = {"pipeline": _draft(expert).pipeline.model_dump(mode="json"), "step": "calls"}
    app.dependency_overrides[get_principal] = lambda: EDITOR
    response = expert.post(f"{RECIPE_URL}/sql-check", json=body)
    assert response.status_code == 403
    assert response.json()["detail"]["right"] == "write_sql_transforms"


def test_check_sql_says_what_the_gate_says(expert: TestClient) -> None:
    graph = _draft(expert).pipeline.model_copy(deep=True)
    assert expert.post(
        f"{RECIPE_URL}/sql-check", json={"pipeline": graph.model_dump(mode="json"), "step": "calls"}
    ).json()["problems"] == []
    _sql_node(graph).config["select"] = "SELECT booking_id FROM titled; SELECT 1"
    checked = expert.post(
        f"{RECIPE_URL}/sql-check", json={"pipeline": graph.model_dump(mode="json"), "step": "calls"}
    ).json()["problems"]
    saved = expert.put(f"{RECIPE_URL}/pipeline", json=graph.model_dump(mode="json")).json()
    assert checked and set(checked) <= set(saved["problems"])


def test_an_expert_step_s_sample_shows_its_rows(expert: TestClient) -> None:
    body = {"pipeline": _draft(expert).pipeline.model_dump(mode="json"), "step": "visitor_owner"}
    response = expert.post(f"{RECIPE_URL}/staging-preview", json=body)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["problems"] == []
    assert "match_score" in preview["columns"] and "_ref" not in str(preview["columns"])
    titles = [row["title"] for row in preview["rows"]]
    assert titles[0].endswith("3 PIN calls") and titles[1].endswith("1 PIN calls")
    counts = {c["step"]: c for c in preview["counts"]}
    assert counts["visitor_owner"]["threshold"] == 0.6
    fuzzy = counts["visitor_owner"]
    # The Join refused the booking with no number ("not given"); the fuzzy match kept the other five.
    assert fuzzy["rows_in"] == fuzzy["rows_out"] == fuzzy["matched"] + fuzzy["unmatched"] == 5


def test_an_expert_step_s_sample_and_test_give_an_uncleared_reader_nothing(
    expert: TestClient,
) -> None:
    """Rule 3: an expert step's author writes its SQL and its comparisons, so either could be made
    to tell a hidden value; the drawer's and Test's guard holds for them as for every step."""
    _draft(expert).handling = _UNCLEARED_HANDLING
    body = {"pipeline": _draft(expert).pipeline.model_dump(mode="json"), "step": "calls"}
    preview = expert.post(f"{RECIPE_URL}/staging-preview", json=body).json()
    assert preview["rows"] == [] and preview["counts"] == []
    assert any(p.startswith("The sample is withheld") for p in preview["problems"])
    for route in ("verify", "preview-graph"):
        response = expert.post(f"{RECIPE_URL}/{route}")
        assert response.status_code == 422, (route, response.text)
        assert "WHITLOW" not in response.text and "PIN calls" not in response.text


def test_test_discloses_both_expert_steps(expert: TestClient) -> None:
    response = expert.post(f"{RECIPE_URL}/verify")
    assert response.status_code == 200, response.text
    body = response.json()
    disclosed = {d["step"]: d for d in body["expert_steps"]}
    assert set(disclosed) == {"calls", "visitor_owner"}
    assert disclosed["calls"]["summary"].startswith("Counts the PIN calls")
    assert disclosed["calls"]["select"].startswith("SELECT t.*")
    assert disclosed["visitor_owner"]["threshold"] == 0.6
    assert disclosed["visitor_owner"]["same_as"] == ["visitor", "matched"]
    assert body["edges_by_type"]["SAME_AS"]["created"] >= 1
    inferred = [e for e in body["edges"] if e["type"] == "SAME_AS"]
    assert {e["provenance"]["state"] for e in inferred} == {"inferred"}


def test_the_threshold_is_deployed_with_the_version(expert: TestClient, git_repo: Path) -> None:
    """ADR-006 Amendment 1 item 4: the threshold is part of the version; a run says which."""
    from services.api.app import get_recipes_repo_root

    app.dependency_overrides[get_recipes_repo_root] = lambda: git_repo
    _draft(expert).verified_at = datetime(2026, 11, 8, tzinfo=UTC)
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER.model_copy(
        update={"datasets": ["pid"]}
    )
    first = expert.post(f"{RECIPE_URL}/publish", json={})
    assert first.status_code == 200, first.text
    published = yaml.safe_load((git_repo / "recipes" / "recipe-1.yaml").read_text())
    fuzzy = next(s for s in published["staging"] if s["kind"] == "fuzzy_match")
    assert (published["version"], fuzzy["threshold"]) == (1, 0.6)
