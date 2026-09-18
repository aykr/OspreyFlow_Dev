"""HTTP route wiring for Publish (`docs/09_INGEST_STUDIO.md` §6) —
`POST .../publish`, `PATCH .../schedule`, `POST .../versions`,
`POST /v1/investigations/{id}/ingest/recipes/{id}/run`. Mirrors
`test_studio_verify_routes.py`'s own discipline: fakes for the store/
investigations/graph, a real (throwaway, per-test) git repository for the
commit `write_and_commit_recipe` actually performs — that repository
mechanics are worth proving for real rather than faked away — and never a
live ArcadeDB or Postgres; `StudioRecipeStore`'s own publish/schedule/
version/flag_stale correctness is proven directly in
`test_studio_recipes_store.py`, and a real end-to-end run (attribution,
and an ontology edit actually blocking a flagged recipe) is proven in
`tests/ingest/test_studio_publish_pipeline.py`. What belongs here is only
"does the right role get through, does the wrong role get a 403, does the
right conflict status come back"."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_graph,
    get_investigations,
    get_ontology,
    get_principal,
    get_recipes_repo_root,
)

from ontology.loader import load_default_ontology
from schemas.ingest import FieldBinding, RecipeEntity, RowTemplate, StudioRecipeStatus
from tests.services.api.test_app import _FakeInvestigations
from tests.services.api.test_studio_recipe_routes import (
    SOURCE_APPROVER,
    SOURCE_AUTHOR,
    _draft,
    _ready_draft,
    client,  # noqa: F401  (reused fixture, extended below)
)

# ruff: noqa: F811  (the imported `client` fixture is shadowed by design — see module docstring)


def _row_template() -> RowTemplate:
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


def _verified_draft(tmp_path: Path, **overrides: object):
    draft = _ready_draft(tmp_path, row_template=_row_template(), **overrides)
    return draft.model_copy(update={"verified_at": datetime(2026, 1, 1, tzinfo=UTC)})


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    return repo


@pytest.fixture
def publish_client(client: TestClient, git_repo: Path) -> TestClient:
    app.dependency_overrides[get_ontology] = lambda: load_default_ontology()
    app.dependency_overrides[get_recipes_repo_root] = lambda: git_repo
    return client


def test_publish_as_source_approver_succeeds(publish_client: TestClient, tmp_path: Path) -> None:
    publish_client.studio_recipes.draft = _verified_draft(tmp_path)  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER

    response = publish_client.post("/v1/ingest/recipes/recipe-1/publish", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "published"
    assert body["git_path"] == "recipes/recipe-1.yaml"
    assert body["published_by"] == "approver-1"


def test_publish_without_approver_role_is_forbidden(
    publish_client: TestClient, tmp_path: Path
) -> None:
    publish_client.studio_recipes.draft = _verified_draft(tmp_path)  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR

    response = publish_client.post("/v1/ingest/recipes/recipe-1/publish", json={})

    assert response.status_code == 403


def test_publish_an_unverified_draft_is_a_conflict(
    publish_client: TestClient, tmp_path: Path
) -> None:
    publish_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, row_template=_row_template()
    )
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER

    response = publish_client.post("/v1/ingest/recipes/recipe-1/publish", json={})

    assert response.status_code == 409
    assert response.json()["error"] == "studio_recipe_not_verified"


def test_publish_writes_and_commits_the_recipe_yaml(
    publish_client: TestClient, tmp_path: Path, git_repo: Path
) -> None:
    publish_client.studio_recipes.draft = _verified_draft(tmp_path)  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER

    response = publish_client.post(
        "/v1/ingest/recipes/recipe-1/publish",
        json={"schedule_cron": "0 6 * * *"},
    )

    assert response.status_code == 200
    yaml_path = git_repo / "recipes" / "recipe-1.yaml"
    assert yaml_path.exists()
    content = yaml_path.read_text()
    assert "schedule" in content
    assert "0 6 * * *" in content
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=git_repo, check=True, capture_output=True, text=True
    )
    assert "publish recipe-1" in log.stdout


def test_schedule_as_source_approver_succeeds(publish_client: TestClient, tmp_path: Path) -> None:
    published = _verified_draft(tmp_path).model_copy(
        update={
            "status": StudioRecipeStatus.PUBLISHED,
            "ontology_version": 1,
            "git_path": "recipes/recipe-1.yaml",
        }
    )
    publish_client.studio_recipes.draft = published  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER

    response = publish_client.patch(
        "/v1/ingest/recipes/recipe-1/schedule",
        json={"schedule_cron": "0 7 * * *", "schedule_watch": None},
    )

    assert response.status_code == 200
    assert response.json()["schedule_cron"] == "0 7 * * *"


def test_schedule_without_approver_role_is_forbidden(
    publish_client: TestClient, tmp_path: Path
) -> None:
    published = _verified_draft(tmp_path).model_copy(
        update={
            "status": StudioRecipeStatus.PUBLISHED,
            "ontology_version": 1,
            "git_path": "recipes/recipe-1.yaml",
        }
    )
    publish_client.studio_recipes.draft = published  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR

    response = publish_client.patch(
        "/v1/ingest/recipes/recipe-1/schedule",
        json={"schedule_cron": "0 7 * * *", "schedule_watch": None},
    )

    assert response.status_code == 403


def test_create_new_version_as_source_author_succeeds(
    publish_client: TestClient, tmp_path: Path
) -> None:
    published = _verified_draft(tmp_path).model_copy(
        update={
            "status": StudioRecipeStatus.PUBLISHED,
            "ontology_version": 1,
            "git_path": "recipes/recipe-1.yaml",
        }
    )
    publish_client.studio_recipes.draft = published  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR

    response = publish_client.post("/v1/ingest/recipes/recipe-1/versions")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["version"] == published.version + 1


def test_create_new_version_from_a_draft_is_a_conflict(
    publish_client: TestClient, tmp_path: Path
) -> None:
    publish_client.studio_recipes.draft = _draft()  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR

    response = publish_client.post("/v1/ingest/recipes/recipe-1/versions")

    assert response.status_code == 409
    assert response.json()["error"] == "studio_recipe_cannot_version"


# --- run (§8: "Loader: run a published recipe") ------------------------------


@pytest.fixture
def run_client(publish_client: TestClient) -> TestClient:
    fake_investigations = _FakeInvestigations()
    app.dependency_overrides[get_investigations] = lambda: fake_investigations
    app.dependency_overrides[get_graph] = lambda: object()
    return publish_client


def test_run_without_loader_role_is_forbidden(run_client: TestClient, tmp_path: Path) -> None:
    published = _verified_draft(tmp_path).model_copy(
        update={
            "status": StudioRecipeStatus.PUBLISHED,
            "ontology_version": 1,
            "git_path": "recipes/recipe-1.yaml",
        }
    )
    run_client.studio_recipes.draft = published  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR

    response = run_client.post("/v1/investigations/inv-1/ingest/recipes/recipe-1/run")

    assert response.status_code == 403
