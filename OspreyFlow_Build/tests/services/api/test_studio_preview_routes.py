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
- an uncleared reader seeing values (`test_a_preview_masks_values_for_a_reader_not_cleared`)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from services.api.app import app, get_audit, get_principal

from tests.services.api.test_app import _FakeAudit
from tests.services.api.test_studio_recipe_routes import (
    _UNCLEARED_HANDLING,
    NO_ROLE_ANALYST,
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


def test_a_preview_masks_values_for_a_reader_not_cleared(
    graph_client: TestClient, tmp_path: Path
) -> None:
    _ready(graph_client, tmp_path, handling=_UNCLEARED_HANDLING)
    body = graph_client.post(f"{RECIPE}/preview-graph").json()
    assert body["values_masked"] is True
    assert "07960112334" not in str(body)
