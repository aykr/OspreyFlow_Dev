"""HTTP route wiring for Publish (`spec/09_INGEST_STUDIO.md` §6) —
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
from typing import Any

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
from tests.services.api.any_case import AnyCase
from tests.services.api.test_app import _FakeInvestigations
from tests.services.api.test_studio_recipe_routes import (
    _UNCLEARED_HANDLING,
    LOADER,
    SOURCE_APPROVER,
    SOURCE_AUTHOR,
    _draft,
    _ready_draft,
    client,  # noqa: F401  (reused fixture, extended below)
)

#: ADR-099 Amendment 3: the Studio's routes are the case's.
CASE = "/v1/investigations/inv-1"

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


def _verified_draft(tmp_path: Path, row_template: RowTemplate | None = None, **overrides: object):
    draft = _ready_draft(tmp_path, row_template=row_template or _row_template(), **overrides)
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
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(f"{CASE}/ingest/recipes/recipe-1/publish", json={})

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
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(f"{CASE}/ingest/recipes/recipe-1/publish", json={})

    assert response.status_code == 403


def _a_draft_naming_niem(tmp_path: Path):
    from schemas.ingest import PipelineGraph

    pipeline = PipelineGraph.model_validate(
        {
            "nodes": [
                {"id": "domain", "kind": "domain_model", "label": "D", "config": {"pack": "niem"}}
            ],
            "edges": [],
        }
    )
    return _verified_draft(tmp_path, pipeline=pipeline)


def test_publishing_a_recipe_naming_a_pack_the_ontology_lacks_is_refused_as_pack_not_composed(
    publish_client: TestClient, tmp_path: Path, git_repo: Path
) -> None:
    """ADR-120 Amendment 1: a pack the ontology in force does not compose cannot be pinned. Red if
    the route answers a 500 (the `ValueError` escaping), publishes with no pin for it, or commits
    the file before it has refused."""
    # `publish_client` serves the core-only ontology, which composes no pack.
    publish_client.studio_recipes.draft = _a_draft_naming_niem(tmp_path)  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(f"{CASE}/ingest/recipes/recipe-1/publish", json={})

    assert response.status_code == 422, response.text
    assert response.json()["error"] == "pack_not_composed"
    assert "niem" in response.json()["message"]
    assert not (git_repo / "recipes" / "recipe-1.yaml").exists()


def test_publishing_another_unit_s_recipe_is_not_found_not_pack_not_composed(
    publish_client: TestClient, tmp_path: Path, git_repo: Path
) -> None:
    """The same draft, published by a principal of another unit, collapses to a 404 like every
    other read of a recipe the principal may not see. Red if the pack check runs before the
    ownership check, which would tell a stranger that the recipe exists and names a pack."""
    from schemas.domain import Principal

    other_unit_approver = Principal(
        id="approver-9", clearance="OFFICIAL", org_unit="unit-2", roles=["source_approver"]
    )
    publish_client.studio_recipes.draft = _a_draft_naming_niem(tmp_path)  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: other_unit_approver
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(f"{CASE}/ingest/recipes/recipe-1/publish", json={})

    assert response.status_code == 404, response.text
    assert response.json()["error"] != "pack_not_composed"
    assert not (git_repo / "recipes" / "recipe-1.yaml").exists()


def test_publish_an_unverified_draft_is_a_conflict(
    publish_client: TestClient, tmp_path: Path
) -> None:
    publish_client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, row_template=_row_template()
    )
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(f"{CASE}/ingest/recipes/recipe-1/publish", json={})

    assert response.status_code == 409
    assert response.json()["error"] == "studio_recipe_not_verified"


def test_publish_writes_and_commits_the_recipe_yaml(
    publish_client: TestClient, tmp_path: Path, git_repo: Path
) -> None:
    publish_client.studio_recipes.draft = _verified_draft(tmp_path)  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(
        f"{CASE}/ingest/recipes/recipe-1/publish",
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


def test_the_publish_route_stamps_the_pins_of_named_and_written_packs(
    publish_client: TestClient, tmp_path: Path, git_repo: Path
) -> None:
    """ADR-120 Amendment 1, decision 6: the route pins the packs the recipe writes as well as the
    ones it names, from the live ontology. Red if the route pins only what the pipeline names (this
    recipe's domain node is the core, so it would pin nothing), passes no pins to the store, or
    stamps the store and not the committed file, which is what a run reads."""
    from services.ingest.recipe_loader import load_recipe

    from ontology.packs import load_deployment_ontology
    from schemas.ingest import PipelineGraph

    app.dependency_overrides[get_ontology] = lambda: load_deployment_ontology()
    pipeline = PipelineGraph.model_validate(
        {
            "nodes": [
                {"id": "domain", "kind": "domain_model", "label": "D", "config": {"pack": "pole"}},
                {"id": "source", "kind": "source", "label": "S", "config": {}},
                {"id": "map", "kind": "map", "label": "M", "config": {}},
                {"id": "load", "kind": "load", "label": "L", "config": {}},
            ],
            "edges": [
                {"source": "domain", "target": "source"},
                {"source": "source", "target": "map"},
                {"source": "map", "target": "load"},
            ],
        }
    )
    writes_account = RowTemplate(
        entities=[
            RecipeEntity(
                ref="a",
                pole_class="object",
                type="Account",
                match_on="account_number",
                on_match="reference",
                properties={"account_number": FieldBinding(field="a_party")},
            )
        ]
    )
    store = publish_client.studio_recipes  # type: ignore[attr-defined]
    store.draft = _verified_draft(tmp_path, row_template=writes_account, pipeline=pipeline)
    received: list[dict[str, object]] = []
    real_publish = store.publish

    async def recording_publish(recipe_id: str, principal: Any, **kwargs: object) -> Any:
        received.append(kwargs)
        return await real_publish(recipe_id, principal, **kwargs)

    store.publish = recording_publish
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(f"{CASE}/ingest/recipes/recipe-1/publish", json={})

    assert response.status_code == 200, response.text
    assert [call["pack_versions"] for call in received] == [{"fibo": 1}]
    committed = load_recipe(git_repo / "recipes" / "recipe-1.yaml")
    assert committed.pack_versions == {"fibo": 1}


def test_schedule_as_source_approver_succeeds(publish_client: TestClient, tmp_path: Path) -> None:
    published = _verified_draft(tmp_path).model_copy(
        update={
            "status": StudioRecipeStatus.PUBLISHED,
            "ontology_version": 1,
            "git_path": "recipes/recipe-1.yaml",
            "pack_versions": {},
        }
    )
    publish_client.studio_recipes.draft = published  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.patch(
        f"{CASE}/ingest/recipes/recipe-1/schedule",
        json={"schedule_cron": "0 7 * * *", "schedule_watch": None},
    )

    assert response.status_code == 200
    assert response.json()["schedule_cron"] == "0 7 * * *"


def _published_row(tmp_path: Path, **update: object):
    return _verified_draft(tmp_path).model_copy(
        update={
            "status": StudioRecipeStatus.PUBLISHED,
            "ontology_version": 1,
            "git_path": "recipes/recipe-1.yaml",
            **update,
        }
    )


def test_a_schedule_change_carries_the_row_s_pins_into_the_committed_file(
    publish_client: TestClient, tmp_path: Path, git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-120 Amendment 1, decision 6 and the coordinator's ruling: a schedule change re-commits
    the recipe with the pins the row already holds. Red if the re-commit builds the recipe with no
    pins or with fresh ones (the committed file then disagrees with the row, and a run reads the
    file), or drops `pack_versions` from the YAML."""
    import services.api.app as app_module
    from services.ingest.recipe_loader import load_recipe

    built_with: list[object] = []
    real_build = app_module.build_recipe

    def recording_build(*args: Any, **kwargs: Any) -> Any:
        built_with.append(kwargs.get("pack_versions"))
        return real_build(*args, **kwargs)

    monkeypatch.setattr(app_module, "build_recipe", recording_build)
    publish_client.studio_recipes.draft = _published_row(  # type: ignore[attr-defined]
        tmp_path, pack_versions={"fibo": 1}
    )
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.patch(
        f"{CASE}/ingest/recipes/recipe-1/schedule",
        json={"schedule_cron": "0 7 * * *", "schedule_watch": None},
    )

    assert response.status_code == 200, response.text
    assert built_with == [{"fibo": 1}]
    committed = load_recipe(git_repo / "recipes" / "recipe-1.yaml")
    assert committed.pack_versions == {"fibo": 1}


def test_a_schedule_change_on_an_unpinned_row_is_saved_and_re_committed_without_pins(
    publish_client: TestClient, tmp_path: Path, git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-120 Amendment 2, decision 2: a row with no pins (flagged before pinning, which the
    backfill never reads) is re-committed with the pins it has, which are none, and the schedule
    is saved. Red if the route refuses it (an analyst could then not pause such a recipe), or
    invents pins (`{}` or the current versions), which would hide a pack bump from that recipe."""
    import services.api.app as app_module
    from services.ingest.recipe_loader import load_recipe

    built_with: list[object] = []
    real_build = app_module.build_recipe

    def recording_build(*args: Any, **kwargs: Any) -> Any:
        built_with.append(kwargs.get("pack_versions", "not passed"))
        return real_build(*args, **kwargs)

    monkeypatch.setattr(app_module, "build_recipe", recording_build)
    publish_client.studio_recipes.draft = _published_row(  # type: ignore[attr-defined]
        tmp_path, pack_versions=None
    )
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.patch(
        f"{CASE}/ingest/recipes/recipe-1/schedule",
        json={"schedule_cron": "0 7 * * *", "schedule_watch": None},
    )

    assert response.status_code == 200, response.text
    assert publish_client.studio_recipes.draft.schedule_cron == "0 7 * * *"  # type: ignore[attr-defined]
    assert built_with == [None]
    committed = load_recipe(git_repo / "recipes" / "recipe-1.yaml")
    assert committed.pack_versions is None
    assert "pack_versions" not in (git_repo / "recipes" / "recipe-1.yaml").read_text()


def test_a_schedule_change_on_a_mapped_row_with_no_ontology_version_is_saved_without_a_re_commit(
    publish_client: TestClient, tmp_path: Path, git_repo: Path
) -> None:
    """ADR-120 Amendment 2, decision 2: a mapped row with no core version has nothing to commit
    against, so the schedule is saved and the re-commit skipped, as the administrator's route
    does. Red if the route saves the schedule and then fails (a 500 after a save), or writes a
    file for a row that has no version to write."""
    publish_client.studio_recipes.draft = _published_row(  # type: ignore[attr-defined]
        tmp_path, ontology_version=None, pack_versions={}
    )
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.patch(
        f"{CASE}/ingest/recipes/recipe-1/schedule",
        json={"schedule_cron": "0 7 * * *", "schedule_watch": None},
    )

    assert response.status_code == 200, response.text
    assert publish_client.studio_recipes.draft.schedule_cron == "0 7 * * *"  # type: ignore[attr-defined]
    assert not (git_repo / "recipes" / "recipe-1.yaml").exists()


@pytest.mark.parametrize(
    ("body", "words"),
    [
        ({"schedule_cron": "every morning"}, "not a schedule"),
        ({"schedule_cron": "*/5 * * * *"}, "more often than every 15 minutes"),
        ({"schedule_cron": "0 7 * * *", "schedule_timezone": "Mars/Olympus"}, "not a time zone"),
    ],
)
def test_a_schedule_it_could_not_keep_is_refused_in_words_and_not_saved(
    publish_client: TestClient, tmp_path: Path, body: dict[str, str], words: str
) -> None:
    """ADR-110 decision 7 (rule 2): refused before anything is saved."""
    published = _verified_draft(tmp_path).model_copy(
        update={
            "status": StudioRecipeStatus.PUBLISHED,
            "ontology_version": 1,
            "git_path": "recipes/recipe-1.yaml",
        }
    )
    publish_client.studio_recipes.draft = published  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.patch(f"{CASE}/ingest/recipes/recipe-1/schedule", json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "schedule_refused"
    assert words in response.json()["detail"]
    assert publish_client.studio_recipes.draft.schedule_cron is None  # type: ignore[attr-defined]


def test_publish_refuses_a_schedule_it_could_not_keep_before_committing(
    publish_client: TestClient, tmp_path: Path, git_repo: Path
) -> None:
    publish_client.studio_recipes.draft = _verified_draft(tmp_path)  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_APPROVER
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(
        f"{CASE}/ingest/recipes/recipe-1/publish", json={"schedule_cron": "61 * * * *"}
    )

    assert response.status_code == 422
    assert not (git_repo / "recipes" / "recipe-1.yaml").exists()


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
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.patch(
        f"{CASE}/ingest/recipes/recipe-1/schedule",
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
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(f"{CASE}/ingest/recipes/recipe-1/versions")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["version"] == published.version + 1


def test_create_new_version_from_a_draft_is_a_conflict(
    publish_client: TestClient, tmp_path: Path
) -> None:
    publish_client.studio_recipes.draft = _draft()  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR
    app.dependency_overrides[get_investigations] = AnyCase

    response = publish_client.post(f"{CASE}/ingest/recipes/recipe-1/versions")

    assert response.status_code == 409
    assert response.json()["error"] == "studio_recipe_cannot_version"


# --- run (§8: "Loader: run a published recipe") ------------------------------


@pytest.fixture
def run_client(publish_client: TestClient) -> TestClient:
    fake_investigations = _FakeInvestigations()
    app.dependency_overrides[get_investigations] = lambda: fake_investigations
    app.dependency_overrides[get_graph] = lambda: object()
    # The stores the run route asks for beyond the load itself (ADR-109's rules, held rows,
    # screening and KYC; the runner is stubbed here): each holds nothing.
    for name in _STUB_STATE:
        if not hasattr(app.state, name):
            setattr(app.state, name, _Empty())
    app.state.recipe_runs = _RecipeRuns()
    return publish_client


_STUB_STATE = ["typology_rules", "held_rows", "screening_lists", "compute", "kyc_expiries"]


class _Empty:
    """A store that holds nothing: every query answers an empty list."""

    def __getattr__(self, _name: str) -> Any:
        async def nothing(*_: Any, **__: Any) -> list[Any]:
            return []

        return nothing


class _RecipeRuns:
    """The run ledger (ADR-110 decision 4) every run is recorded in: what was asked of it."""

    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.finished: list[str] = []
        self.failed: list[str] = []

    async def start(self, **row: Any) -> str:
        self.started.append(row)
        return f"run-{len(self.started)}"

    async def finish(self, run_id: str, **_: Any) -> None:
        self.finished.append(run_id)

    async def fail(self, run_id: str, *_: Any, **__: Any) -> None:
        self.failed.append(run_id)


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
    app.dependency_overrides[get_investigations] = AnyCase

    response = run_client.post(f"{CASE}/ingest/recipes/recipe-1/run")

    assert response.status_code == 403


# 9 October 2026, the data engineer's journey: an OFFICIAL loader ran an OFFICIAL-SENSITIVE recipe,
# twice. Its `on_match: reference` lookups run at the loader's clearance, so the second run could
# not see the numbers the first had made and made them again: two nodes for one number. §8 lets a
# loader run a published recipe only "against a file at or below their own clearance".
def test_a_loader_not_cleared_for_the_source_cannot_run_it(
    run_client: TestClient, tmp_path: Path
) -> None:
    published = _verified_draft(tmp_path, handling=_UNCLEARED_HANDLING).model_copy(
        update={
            "status": StudioRecipeStatus.PUBLISHED,
            "ontology_version": 1,
            "git_path": "recipes/recipe-1.yaml",
        }
    )
    run_client.studio_recipes.draft = published  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: LOADER
    app.dependency_overrides[get_investigations] = AnyCase

    response = run_client.post(f"{CASE}/ingest/recipes/recipe-1/run")

    # The graph stand-in is a bare `object()`: had the run started, it would have failed on it.
    assert response.status_code == 403, response.text
    assert response.json()["error"] == "source_above_clearance"


def test_a_pipeline_recipe_runs_through_the_pipeline_runner(
    run_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-108 phase C's dispatch, rule 12's question answered: if the run route quietly fell
    back to `run_published_recipe` for a recipe holding a pipeline, the response here would be a
    single `LoadReport` and this test — not the live runner suite, which never crosses HTTP —
    is what fails. The runner itself is proven in `tests/ingest/test_pipeline_run.py`."""
    from schemas.ingest import (
        BranchRunReport,
        LoadReport,
        PipelineGraph,
        PipelineRunReport,
    )

    pipeline = PipelineGraph.model_validate(
        {
            "nodes": [
                {"id": "domain", "kind": "domain_model", "label": "D", "config": {"pack": "pole"}},
                {"id": "source", "kind": "source", "label": "A", "config": {}},
                {"id": "source-b", "kind": "source", "label": "B", "config": {}},
                {"id": "map", "kind": "map", "label": "Map", "config": {}},
                {"id": "load", "kind": "load", "label": "Load", "config": {}},
            ],
            "edges": [
                {"source": "domain", "target": "source"},
                {"source": "domain", "target": "source-b"},
                {"source": "source", "target": "map"},
                {"source": "source-b", "target": "map"},
                {"source": "map", "target": "load"},
            ],
        }
    )
    published = _verified_draft(tmp_path).model_copy(
        update={
            "status": StudioRecipeStatus.PUBLISHED,
            "ontology_version": 1,
            "git_path": "recipes/recipe-1.yaml",
            "pipeline": pipeline,
        }
    )
    run_client.studio_recipes.draft = published  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: LOADER
    app.dependency_overrides[get_investigations] = AnyCase
    # The success path resolves the route's whole dependency list; none of these is reached
    # past the (monkeypatched) runner because the fake report creates nothing.
    import services.api.app as app_module

    for getter in (
        app_module.get_analytics,
        app_module.get_media,
        app_module.get_jobs,
        app_module.get_valkey,
        app_module.get_hotlists_store,
        app_module.get_monitors_store,
        app_module.get_patterns_store,
        app_module.get_alerts_store,
        app_module.get_principal_resolver,
        app_module.get_extraction_candidates,
    ):
        app.dependency_overrides[getter] = lambda: object()
    # The run reads one setting, whether a load queues post-ingest resolution (ADR-127 Amendment 33).
    from types import SimpleNamespace

    app.dependency_overrides[app_module.get_config] = lambda: SimpleNamespace(post_ingest_resolution=True)
    app.dependency_overrides[app_module.get_pipeline_recogniser_for] = lambda: (lambda name: None)
    app.dependency_overrides[app_module.get_online_geocode] = lambda: None

    async def fake_runner(draft, principal, **kwargs):
        def branch(source_id: str) -> BranchRunReport:
            return BranchRunReport(
                source_id=source_id,
                source_label=source_id,
                report=LoadReport(
                    load_id=f"{kwargs['load_id']}:{source_id}",
                    recipe_id=draft.recipe_id,
                    recipe_version=draft.version,
                ),
            )

        return PipelineRunReport(
            load_id=kwargs["load_id"],
            recipe_id=draft.recipe_id,
            recipe_version=draft.version,
            branches=[branch("source"), branch("source-b")],
        )

    monkeypatch.setattr("services.api.recipe_run.run_published_pipeline", fake_runner)

    response = run_client.post(f"{CASE}/ingest/recipes/recipe-1/run", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [b["source_id"] for b in body["branches"]] == ["source", "source-b"]


async def test_an_admin_change_of_schedule_is_re_committed_to_the_recipe_yaml(
    tmp_path: Path, git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-110 Amendment 3, point 2: the recipe repository stays the record of a schedule. The row
    pins `{"niem": 2}` on a recipe whose own mapping names no pack, so recomputing the pins would
    give `{}`: red if the re-commit recomputes them instead of carrying the row's."""
    import services.api.app as app_module
    from services.api.app import _commit_schedule

    built_with: list[object] = []
    real_build = app_module.build_recipe

    def recording_build(*args: Any, **kwargs: Any) -> Any:
        built_with.append(kwargs.get("pack_versions", "not passed"))
        return real_build(*args, **kwargs)

    monkeypatch.setattr(app_module, "build_recipe", recording_build)
    recipe = _verified_draft(tmp_path).model_copy(
        update={"status": StudioRecipeStatus.PUBLISHED, "ontology_version": 1,
                "schedule_cron": "30 7 * * 1-5", "git_path": "recipes/recipe-1.yaml",
                "pack_versions": {"niem": 2}}
    )  # fmt: skip
    await _commit_schedule(recipe, git_repo)
    assert "30 7 * * 1-5" in (git_repo / "recipes" / "recipe-1.yaml").read_text()
    from services.ingest.recipe_loader import load_recipe

    assert built_with == [{"niem": 2}]
    assert load_recipe(git_repo / "recipes" / "recipe-1.yaml").pack_versions == {"niem": 2}
