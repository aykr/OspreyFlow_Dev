"""HTTP route wiring for Verify (`spec/09_INGEST_STUDIO.md` §5) —
`POST /v1/investigations/{id}/ingest/recipes/{recipe}/verify`. Mirrors `test_studio_map_routes.py`'s
own discipline: a fake store and a fake `GraphPort`, never a live ArcadeDB —
`dry_run_recipe`'s own correctness (including the access-control mechanism)
is proven against a real one in `tests/ingest/test_verify_dry_run.py`; what
belongs here is only "does the right role get through, does org-unit
scoping collapse to a 404, does a missing row template become a 409" — the
same route-wiring questions every other studio route test asks."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_graph, get_ontology, get_recipe_runs

from ontology.loader import load_default_ontology
from schemas.domain import Node, Principal
from schemas.ingest import (
    FieldBinding,
    RecipeEntity,
    RowTemplate,
)
from tests.services.api.test_studio_recipe_routes import (
    _UNCLEARED_HANDLING,
    _ready_draft,
    _write_csv,
    client,  # noqa: F401  (reused fixture, extended below)
)

# ruff: noqa: F811  (the imported `client` fixture is shadowed by design — see module docstring)


class _FakeGraphPort:
    """Only `find_node` — the one `GraphPort` method Verify's dry run ever
    calls. Configure `find_node_result` per test; a fresh id is always
    generated for a "would create" element regardless, so most tests here
    never need this to return anything but `None`."""

    def __init__(self, find_node_result: Node | None = None) -> None:
        self.find_node_result = find_node_result
        self.find_node_calls: list[tuple[str, str, str, Principal]] = []

    async def find_node(
        self, entity_type: str, identifier_field: str, value: str, principal: Principal
    ) -> Node | None:
        self.find_node_calls.append((entity_type, identifier_field, value, principal))
        return self.find_node_result


class _FakeRunKeys:
    """The ledger's one question Verify asks (ADR-127 decision 5): which row keys the case already
    kept for the recipe. Records what it was asked, and answers from `kept`."""

    def __init__(self) -> None:
        self.already: set[str] = set()
        #: The definitions the case's kept keys were made under, with how many loads each.
        self.made_under: dict[str, int] = {}
        self.asked: list[tuple[str, str, list[str]]] = []

    async def kept_row_keys(self, recipe_id: str, case: str, keys: list[str]) -> set[str]:
        self.asked.append((recipe_id, case, list(keys)))
        return {k for k in keys if k in self.already}

    async def kept(self, recipe_id: str, case: str, keys: list[str]) -> set[str]:
        return await self.kept_row_keys(recipe_id, case, keys)

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
        return dict(self.made_under)


@pytest.fixture
def graph_client(client: TestClient) -> TestClient:
    """`client` (imported above) already overrides principal/store/audit/
    scheme; this adds the dependencies only Verify's route needs: a graph, the ontology and the run
    ledger (which the real app's lifespan always sets: `test_the_lifespan_always_builds_the_run_
    ledger_before_it_serves`)."""
    fake_graph = _FakeGraphPort()
    fake_runs = _FakeRunKeys()
    app.dependency_overrides[get_graph] = lambda: fake_graph
    app.dependency_overrides[get_ontology] = lambda: load_default_ontology()
    app.dependency_overrides[get_recipe_runs] = lambda: fake_runs
    client.fake_graph = fake_graph  # type: ignore[attr-defined]
    client.fake_runs = fake_runs  # type: ignore[attr-defined]
    return client


def _create_only_row_template() -> RowTemplate:
    return RowTemplate(
        entities=[
            RecipeEntity(
                ref="a",
                pole_class="object",
                type="Endpoint",
                on_match="create",
                properties={
                    "value_normalised": FieldBinding(field="a_party"),
                    "endpoint_kind": FieldBinding(literal="msisdn"),
                },
            )
        ]
    )


def test_verify_as_source_author_succeeds(graph_client: TestClient, tmp_path: Path) -> None:
    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, row_template=_create_only_row_template()
    )

    response = graph_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/verify")

    assert response.status_code == 200
    body = response.json()
    assert body["entities_by_type"]["Endpoint"] == {"created": 1, "referenced": 0}
    assert len(body["nodes"]) == 1
    assert body["values_masked"] is False


def test_verify_before_a_row_template_is_saved_is_a_conflict(
    graph_client: TestClient, tmp_path: Path
) -> None:
    graph_client.studio_recipes.draft = _ready_draft(tmp_path)  # type: ignore[attr-defined]

    response = graph_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/verify")

    assert response.status_code == 409
    assert response.json()["error"] == "row_template_missing"


def test_verify_before_profile_has_run_is_a_conflict(graph_client: TestClient) -> None:
    from tests.services.api.test_studio_recipe_routes import _draft

    graph_client.studio_recipes.draft = _draft(  # type: ignore[attr-defined]
        row_template=_create_only_row_template()
    )

    response = graph_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/verify")

    assert response.status_code == 409
    assert response.json()["error"] == "recipe_not_ready_for_profile"


def test_verify_for_a_recipe_in_a_different_unit_is_not_found(
    graph_client: TestClient, tmp_path: Path
) -> None:
    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, row_template=_create_only_row_template(), owning_unit="unit-2"
    )

    response = graph_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/verify")

    assert response.status_code == 404
    assert response.json()["error"] == "studio_recipe_not_found"


# --- The rejection report, for a principal not cleared for the source ----------------------
#
# 9 October 2026, the data engineer's journey: Verify said "You aren't cleared for this source's
# handling marking, so every value this run would create is shown shape-masked", then listed each
# rejected row in full (`'a_party': '+44 7700 900900'`) under a reason quoting the bad value
# (`msisdn: cannot normalise '07ABC 123456'`). The would-be nodes and edges were masked; the
# rejections were not. And because the reason carried the value, two bad values of one cause were
# two groups, where §5 groups by cause.


def _rejecting_row_template() -> RowTemplate:
    return RowTemplate(
        entities=[
            RecipeEntity(
                ref="a",
                pole_class="object",
                type="Endpoint",
                on_match="create",
                properties={
                    "value_normalised": FieldBinding(field="a_party", transform="msisdn"),
                    "endpoint_kind": FieldBinding(literal="msisdn"),
                },
            )
        ]
    )


_BAD_ROWS = [
    {"a_party": "07700900461", "duration": "42"},
    {"a_party": "07ABC 123456", "duration": "45"},
    {"a_party": "07XYZ 654321", "duration": "12"},
]


def test_an_uncleared_principal_sees_no_rejected_value(
    graph_client: TestClient, tmp_path: Path
) -> None:
    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path,
        source_location=_write_csv(tmp_path, _BAD_ROWS),
        handling=_UNCLEARED_HANDLING,
        row_template=_rejecting_row_template(),
    )
    body = graph_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/verify").json()
    assert body["values_masked"] is True
    report = str(body["rejections"])
    for value in ("07ABC 123456", "07XYZ 654321", "123456", "654321", "ABC", "XYZ"):
        assert value not in report, f"{value!r} is in the masked rejection report: {report}"
    assert body["rejections"], "the rows were still rejected"


def test_rejections_are_grouped_by_cause_not_by_value(
    graph_client: TestClient, tmp_path: Path
) -> None:
    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path,
        source_location=_write_csv(tmp_path, _BAD_ROWS),
        row_template=_rejecting_row_template(),
    )
    body = graph_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/verify").json()
    assert body["values_masked"] is False
    assert [(g["count"], len(g["samples"])) for g in body["rejections"]] == [(2, 2)]
    # A cleared principal still sees each rejected row as it was read.
    samples = " ".join(s["sample"] for s in body["rejections"][0]["samples"])
    assert "07ABC 123456" in samples and "07XYZ 654321" in samples


def test_the_lifespan_always_builds_the_run_ledger_before_it_serves() -> None:
    """Verify (and the run routes) take the ledger from `app.state.recipe_runs`. The lifespan
    connects it and sets it as plain statements of its own body, under no `if` and no profile
    check, so every deployment (lite included) has one before the first request is served."""
    import ast

    source = (
        Path(__file__).resolve().parents[4] / "OspreyFlow_Core/services/api/app.py"
    ).read_text(encoding="utf-8")
    lifespan = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"
    )
    connected = [
        n
        for n in lifespan.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "recipe_runs" for t in n.targets)
    ]
    assigned = [
        n
        for n in lifespan.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Attribute) and t.attr == "recipe_runs" for t in n.targets)
    ]
    assert len(connected) == 1 and len(assigned) == 1


def test_verify_counts_the_rows_the_case_already_kept_for_the_drafts_own_deduplicate(
    graph_client: TestClient, tmp_path: Path
) -> None:
    from services.ingest.engine import dedup_key

    from schemas.ingest import DeduplicateConfig

    rows = [
        {"a_party": "07960112334", "duration": "42"},
        {"a_party": "07960112335", "duration": "43"},
        {"a_party": "07960112336", "duration": "44"},
    ]
    dedupe = DeduplicateConfig(key=[FieldBinding(field="a_party")])
    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path,
        source_location=_write_csv(tmp_path, rows),
        row_template=_create_only_row_template(),
        deduplicate=dedupe,
    )
    keys = [dedup_key(r, dedupe.key) for r in rows]
    graph_client.fake_runs.already = {keys[0], keys[1]}  # type: ignore[attr-defined]

    response = graph_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/verify")

    assert response.status_code == 200
    body = response.json()
    assert (body["rows_read"], body["rows_already_loaded"]) == (3, 2)
    (asked,) = graph_client.fake_runs.asked  # type: ignore[attr-defined]
    assert asked[0] == "recipe-1" and asked[1] == "inv-1", "this recipe, this case: no other"
    assert body["entities_by_type"]["Endpoint"]["created"] == 1, "only the new row is simulated"


def test_verify_of_a_draft_with_no_deduplicate_asks_the_ledger_nothing(
    graph_client: TestClient, tmp_path: Path
) -> None:
    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, row_template=_create_only_row_template()
    )
    response = graph_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/verify")
    assert response.status_code == 200 and response.json()["rows_already_loaded"] == 0
    assert graph_client.fake_runs.asked == []  # type: ignore[attr-defined]


def test_verify_is_refused_in_words_when_the_drafts_deduplicate_is_not_the_one_the_keys_were_made_under(
    graph_client: TestClient, tmp_path: Path
) -> None:
    from schemas.ingest import DeduplicateConfig

    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path,
        row_template=_create_only_row_template(),
        deduplicate=DeduplicateConfig(key=[FieldBinding(field="a_party")]),
    )
    graph_client.fake_runs.made_under = {"an-earlier-definition": 3}  # type: ignore[attr-defined]

    response = graph_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/verify")

    assert response.status_code == 409
    body = response.json()
    assert (body["error"], body["loads"]) == ("deduplicate_changed", 3)
    assert "3 load(s)" in body["message"] and "an-earlier-definition" not in response.text
    assert graph_client.studio_recipes.draft.verified_at is None  # type: ignore[attr-defined]
