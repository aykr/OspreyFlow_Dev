"""Phase 6's graph *Preview* at the route (ADR-140 decision 14; ADR-140 Amendment 8 point 2):
`POST /v1/investigations/{id}/ingest/recipes/{recipe}/preview-graph` is the dry run `verify` runs,
and it writes nothing that counts as Test.

The review of L1.2 (7 November 2026) found the first build's Map and Load Preview calling `verify`.
That call marks the draft verified, which is the flag Deploy's gate reads, records the source files
a run is held to, and writes a `verify_studio_recipe` audit row. So a Preview silently satisfied
Deploy, and the audit could not tell a Preview from a Test. What a mistake would do, and the case
that catches it:

- a Preview marking the draft verified or recording its files
  (`test_a_preview_leaves_the_draft_unverified_and_records_no_files`);
- a Preview auditing as a Test (`test_a_preview_is_audited_as_a_preview_never_as_a_test`);
- the Preview not being the same dry run, so the two disagree
  (`test_a_preview_shows_the_graph_test_would_show`);
- the Preview widening who may read the graph: Test's right and level, a recipe of another unit
  hidden (`test_a_preview_needs_tests_right`,
  `test_a_preview_of_another_units_recipe_is_not_found`);
- an uncleared reader seeing values (`test_a_preview_masks_values_for_a_reader_not_cleared`);
- main's current reach, the same through every door (the third review of L1.2): a case whose read
  set holds the recipe's dataset reaches it through open (Preview, Test) and through both lists,
  even a case that only reads the dataset; another unit, and a viewer, are refused
  (`test_a_case_reading_the_dataset_reaches_the_recipe_through_open_and_both_lists`,
  `test_another_units_recipe_is_refused_through_open_and_both_lists`,
  `test_a_viewer_of_the_case_is_refused_preview_and_test`). The owner's ruling of 7 November, that
  only a case loading into a dataset lists or opens its pipelines, is a store query the next step
  (L1.2a) builds after L3.1; these cases change with it."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_investigations,
    get_principal,
    get_recipes_repo_root,
)
from services.api.investigations import AccessLevel, InsufficientAccessError, Investigation

from schemas.domain import Principal
from tests.services.api.any_case import AnyCase
from tests.services.api.test_app import _FakeAudit
from tests.services.api.test_studio_publish_routes import git_repo  # noqa: F401  (a fixture)
from tests.services.api.test_studio_recipe_routes import (
    _UNCLEARED_HANDLING,
    NO_ROLE_ANALYST,
    SOURCE_APPROVER,
    SOURCE_AUTHOR,
    _ready_draft,
)
from tests.services.api.test_studio_verify_routes import (  # noqa: F401  (fixtures)
    _create_only_row_template,
    client,
    graph_client,
)

# ruff: noqa: F811  (the imported fixtures are every test's own same-named parameters)

RECIPE = "/v1/investigations/inv-1/ingest/recipes/recipe-1"


def _ready(graph_client: TestClient, tmp_path: Path, **overrides: object) -> None:
    graph_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, row_template=_create_only_row_template(), **overrides
    )


def _audited(graph_client: TestClient) -> _FakeAudit:
    audit = _FakeAudit()
    app.dependency_overrides[get_audit] = lambda: audit
    return audit


def test_a_preview_leaves_the_draft_unverified_and_records_no_files(
    graph_client: TestClient, tmp_path: Path
) -> None:
    _ready(graph_client, tmp_path)
    response = graph_client.post(f"{RECIPE}/preview-graph")
    assert response.status_code == 200
    assert graph_client.studio_recipes.draft.verified_at is None  # type: ignore[attr-defined]
    assert graph_client.studio_recipes.verified == {}  # type: ignore[attr-defined]


def test_a_preview_is_audited_as_a_preview_never_as_a_test(
    graph_client: TestClient, tmp_path: Path
) -> None:
    _ready(graph_client, tmp_path)
    audit = _audited(graph_client)
    assert graph_client.post(f"{RECIPE}/preview-graph").status_code == 200
    actions = [r["action"] for r in audit.records]
    assert actions == ["preview_studio_recipe_graph"]


def test_a_preview_shows_the_graph_test_would_show(
    graph_client: TestClient, tmp_path: Path
) -> None:
    _ready(graph_client, tmp_path)
    preview = graph_client.post(f"{RECIPE}/preview-graph").json()
    test = graph_client.post(f"{RECIPE}/verify").json()
    assert (
        preview["entities_by_type"]
        == test["entities_by_type"]
        == {"Endpoint": {"created": 1, "referenced": 0}}
    )
    assert preview["rows_read"] == test["rows_read"]
    # Test, run after, is still what marks the draft.
    assert graph_client.studio_recipes.draft.verified_at is not None  # type: ignore[attr-defined]


def test_deploy_is_refused_after_a_preview_until_test_runs(
    graph_client: TestClient, tmp_path: Path, git_repo: Path
) -> None:
    """The store's own gate, `StudioRecipeStore.publish`'s 409, is what a Preview must not open."""
    _ready(graph_client, tmp_path)
    app.dependency_overrides[get_recipes_repo_root] = lambda: git_repo
    assert graph_client.post(f"{RECIPE}/preview-graph").status_code == 200
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    refused = graph_client.post(f"{RECIPE}/publish", json={})
    assert refused.status_code == 409
    assert refused.json()["error"] == "studio_recipe_not_verified"


def test_a_preview_needs_tests_right(graph_client: TestClient, tmp_path: Path) -> None:
    _ready(graph_client, tmp_path)
    app.dependency_overrides[get_principal] = lambda: NO_ROLE_ANALYST
    response = graph_client.post(f"{RECIPE}/preview-graph")
    assert response.status_code == 403


def test_a_preview_of_another_units_recipe_is_not_found(
    graph_client: TestClient, tmp_path: Path
) -> None:
    _ready(graph_client, tmp_path, owning_unit="unit-2")
    response = graph_client.post(f"{RECIPE}/preview-graph")
    assert response.status_code == 404
    assert response.json()["error"] == "studio_recipe_not_found"


def test_a_preview_gives_nothing_to_a_reader_not_cleared(
    graph_client: TestClient, tmp_path: Path
) -> None:
    """Rule 3 (carried from L1.4's independent review): once masked, now withheld whole."""
    _ready(graph_client, tmp_path, handling=_UNCLEARED_HANDLING)
    response = graph_client.post(f"{RECIPE}/preview-graph")
    assert response.status_code == 422
    assert any(p.startswith("The test is withheld") for p in response.json()["problems"])
    assert "07960112334" not in response.text


# --- Main's current reach, the same through open and both lists --------------------------------


def _in_case(datasets: list[str]) -> Principal:
    """The principal `get_principal` gives a case route: scoped to the path case's datasets, the
    one it loads into first (`dataset_scope.scope_to_case`)."""
    return SOURCE_AUTHOR.model_copy(update={"datasets": datasets})


LISTS = (
    "/v1/investigations/inv-1/ingest/recipes",
    "/v1/investigations/inv-1/ingest/recipe-registry",
)


@pytest.mark.parametrize("datasets", [["ds-a"], ["ds-b", "ds-a"]], ids=["loads-into", "only-reads"])
def test_a_case_reading_the_dataset_reaches_the_recipe_through_open_and_both_lists(
    graph_client: TestClient, tmp_path: Path, datasets: list[str]
) -> None:
    _ready(graph_client, tmp_path, dataset_id="ds-a")
    app.dependency_overrides[get_principal] = lambda: _in_case(datasets)
    assert graph_client.post(f"{RECIPE}/preview-graph").status_code == 200
    assert graph_client.post(f"{RECIPE}/verify").status_code == 200
    for listed in LISTS:
        response = graph_client.get(listed)
        assert response.status_code == 200
        assert [d["recipe_id"] for d in response.json()] == ["recipe-1"]


def test_another_units_recipe_is_refused_through_open_and_both_lists(
    graph_client: TestClient, tmp_path: Path
) -> None:
    _ready(graph_client, tmp_path, owning_unit="unit-2")
    for route in ("preview-graph", "verify"):
        assert graph_client.post(f"{RECIPE}/{route}").status_code == 404
    for listed in LISTS:
        assert graph_client.get(listed).json() == []


class _ViewerOnly(AnyCase):
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        if need != AccessLevel.VIEWER:
            raise InsufficientAccessError(f"{need.value} needed")
        return await super().get_authorized(investigation_id, principal, need=need)


@pytest.mark.parametrize("route", ["preview-graph", "verify"])
def test_a_viewer_of_the_case_is_refused_preview_and_test(
    graph_client: TestClient, tmp_path: Path, route: str
) -> None:
    _ready(graph_client, tmp_path)
    app.dependency_overrides[get_investigations] = _ViewerOnly
    assert graph_client.post(f"{RECIPE}/{route}").status_code == 403
    assert graph_client.studio_recipes.draft.verified_at is None  # type: ignore[attr-defined]
