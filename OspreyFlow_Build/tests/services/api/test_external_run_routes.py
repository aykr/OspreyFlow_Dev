"""The run API's and *Owned externally*'s routes (`06_DECISIONS.md` ADR-141 decisions 9-11 and its
named tests; rules 3 and 4; the lane review of L1.7, item 1):

- `POST /v1/runs`: a service identity with no grant to trigger a pipeline is refused, the same
  404 as a pipeline that does not exist or is in another dataset; a pinned version that is not the
  deployed one is 409 in words; a granted trigger reaches the run as the pipeline's owner, the
  person who marked it, never as the identity;
- *Owned externally*: marked only on a deployed pipeline with no schedule of its own (409 in words
  otherwise), the marker its owner in their case; read and taken back; the schedule's own route
  refuses a schedule while it is owned externally;
- the Runs tab's quota bar reads the dataset's quota and today's count, and nothing else.

The recipe store is this file's double, refusing as the real one refuses for these calls (a
recipe of another unit is not found); the run itself is `test_external_runs_live.py`'s.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api.app import (
    app,
    get_audit,
    get_handling_scheme,
    get_investigations,
    get_principal,
    get_principal_resolver,
    get_recipe_runs,
    get_recipes_repo_root,
    get_run_quotas,
    get_studio_recipes,
    get_valkey,
)
from services.api.run_quotas import InMemoryQuotaStore
from services.api.service_identity import ServiceIdentityRefused
from services.api.studio_recipes import ExternalOwner, StudioRecipeNotFoundError

from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from schemas.operations import ExternalRunStatus, RunQuota
from tests.services.api.any_case import AnyCase
from tests.services.api.test_app import _FakeAudit

APPROVER = Principal(
    id="approver-1", clearance="OFFICIAL", org_unit="unit-1",
    roles=["source_approver", "loader", "right:schedule_pipelines"],
)  # fmt: skip
_AT = datetime(2026, 11, 10, tzinfo=UTC)
_BEARER = {"Authorization": "Bearer a-client-credentials-token"}
_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "u",
    "owning_unit": "unit-1",
}


def _deployed(**changes: object) -> StudioRecipeDraft:
    data: dict[str, object] = {
        "recipe_id": "rcp-1", "version": 3, "status": StudioRecipeStatus.PUBLISHED,
        "label": "Visits",
        "handling": _HANDLING, "owning_unit": "unit-1", "created_by": "author-1", "created_at": _AT,
        "ready_for_profile": True, "dataset_id": "pid",
    }  # fmt: skip
    data.update(changes)
    return StudioRecipeDraft.model_validate(data)


class _Recipes:
    def __init__(self, recipe: StudioRecipeDraft, owner: ExternalOwner | None = None) -> None:
        self.recipe, self.owner = recipe, owner

    async def get(self, recipe_id: str) -> StudioRecipeDraft:
        if recipe_id != self.recipe.recipe_id:
            raise StudioRecipeNotFoundError(recipe_id)
        return self.recipe

    async def get_authorized(self, recipe_id: str, principal: Principal) -> StudioRecipeDraft:
        recipe = await self.get(recipe_id)
        if recipe.owning_unit != principal.org_unit:
            raise StudioRecipeNotFoundError(recipe_id)
        return recipe

    async def deployed(self, recipe_id: str) -> StudioRecipeDraft | None:
        ok = (
            recipe_id == self.recipe.recipe_id
            and self.recipe.status is StudioRecipeStatus.PUBLISHED
        )
        return self.recipe if ok else None

    async def external_owner(self, recipe_id: str) -> ExternalOwner | None:
        return self.owner if recipe_id == self.recipe.recipe_id else None

    async def set_external_owner(self, recipe_id: str, *, client_id: str, owner: str, case: str,
                                 now: datetime) -> None:  # fmt: skip
        self.owner = ExternalOwner(recipe_id, client_id, owner, case)

    async def clear_external_owner(self, recipe_id: str) -> None:
        self.owner = None


class _Verifier:
    def __init__(self, client: str | None) -> None:
        self.client = client

    def client_of(self, token: str) -> str:
        if self.client is None:
            raise ServiceIdentityRefused("not a service identity's", status=403)
        return self.client


class _Runs:
    async def runs_since(self, **_: object) -> int:
        return 2


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """`start_external_run`, as reached: who it would act as, for which client, at which version."""
    calls: list[dict[str, Any]] = []

    async def fake(**kwargs: Any) -> ExternalRunStatus:
        calls.append(kwargs)
        return ExternalRunStatus(
            run_id="run-1", pipeline_id="rcp-1", version=3, external_run_id="dag:1",
            outcome="running", started_at=_AT,
        )  # fmt: skip

    monkeypatch.setattr(app_module, "start_external_run", fake)
    monkeypatch.setattr(
        app_module.RecipeRunDeps, "from_state", classmethod(lambda cls, state: object())
    )
    return calls


def _install(recipes: _Recipes, *, client: str | None = "airflow-prod") -> TestClient:
    app.state.service_identities = _Verifier(client)
    app.state.external_runs = set()
    app.dependency_overrides.update({
        get_principal: lambda: APPROVER,
        get_studio_recipes: lambda: recipes,
        get_investigations: AnyCase,
        get_audit: lambda: _FakeAudit(),
        get_handling_scheme: load_uk_le_scheme,
        get_recipe_runs: _Runs,
        get_recipes_repo_root: lambda: Path("/nonexistent-recipes-root"),
        get_valkey: lambda: object(),
        get_principal_resolver: lambda: object(),
    })  # fmt: skip
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()
    for name in ("service_identities", "external_runs", "schedule_executor"):
        if hasattr(app.state, name):
            delattr(app.state, name)


_RUN = {
    "dataset_id": "pid",
    "pipeline_id": "rcp-1",
    "version": "latest",
    "external_run_id": "dag:1",
}
_GRANT = ExternalOwner("rcp-1", "airflow-prod", "approver-1", "case-1")


@pytest.mark.parametrize(
    ("owner", "body", "status"),
    [
        (None, _RUN, 404),
        (ExternalOwner("rcp-1", "another-client", "approver-1", "case-1"), _RUN, 404),
        (_GRANT, {**_RUN, "dataset_id": "another"}, 404),
        (_GRANT, {**_RUN, "pipeline_id": "rcp-none"}, 404),
        (_GRANT, {**_RUN, "version": 2}, 409),
    ],
    ids=[
        "not-owned-externally",
        "another-client",
        "another-dataset",
        "no-such-pipeline",
        "a-stale-pin",
    ],
)
def test_a_trigger_without_the_pipelines_grant_is_refused(
    started: list[dict[str, Any]], owner: ExternalOwner | None, body: dict[str, object], status: int
) -> None:
    app.state.schedule_executor = object()
    answer = _install(_Recipes(_deployed(), owner)).post("/v1/runs", headers=_BEARER, json=body)
    assert answer.status_code == status, answer.text
    assert started == []
    if status == 404:
        assert "triggered only by the client it is owned externally by" in answer.text
    else:
        assert "deployed version is 3, not 2" in answer.text


def test_a_granted_trigger_runs_as_the_owner_who_marked_it(started: list[dict[str, Any]]) -> None:
    app.state.schedule_executor = object()
    answer = _install(_Recipes(_deployed(), _GRANT)).post(
        "/v1/runs", headers=_BEARER, json={**_RUN, "version": 3}
    )
    assert answer.status_code == 202, answer.text
    (call,) = started
    assert (call["recipe"].schedule_owner, call["recipe"].schedule_case) == ("approver-1", "case-1")
    assert call["recipe"].owned_externally_by == "airflow-prod"
    assert (call["external"].run_id, call["external"].triggered_by) == ("dag:1", "airflow-prod")


def test_a_persons_token_is_refused_by_the_run_api(started: list[dict[str, Any]]) -> None:
    app.state.schedule_executor = object()
    answer = _install(_Recipes(_deployed(), _GRANT), client=None).post(
        "/v1/runs", headers=_BEARER, json=_RUN
    )
    assert answer.status_code == 403 and started == []


_OWNED = "/v1/investigations/inv-1/ingest/recipes/rcp-1/owned-externally"


def test_a_pipeline_is_marked_owned_externally_by_its_marker_read_and_taken_back() -> None:
    recipes = _Recipes(_deployed())
    client = _install(recipes)
    assert client.get(_OWNED).json() is None
    answer = client.put(_OWNED, json={"client_id": "airflow-prod"})
    assert answer.status_code == 200, answer.text
    assert recipes.owner == ExternalOwner("rcp-1", "airflow-prod", "approver-1", "inv-1")
    assert client.get(_OWNED).json() == {"client_id": "airflow-prod"}
    assert "approver-1" not in client.get(_OWNED).text
    assert client.delete(_OWNED).status_code == 204 and recipes.owner is None


@pytest.mark.parametrize(
    ("recipe", "words"),
    [
        (
            _deployed(status=StudioRecipeStatus.DRAFT),
            "only a deployed pipeline can be owned externally",
        ),
        (_deployed(schedule_cron="0 6 * * *"), "has a schedule of its own: clear it first"),
        (_deployed(schedule_watch="*.csv"), "has a schedule of its own: clear it first"),
    ],
    ids=["a-draft", "a-schedule", "a-watch"],
)
def test_owned_externally_is_refused_in_words(recipe: StudioRecipeDraft, words: str) -> None:
    recipes = _Recipes(recipe)
    answer = _install(recipes).put(_OWNED, json={"client_id": "airflow-prod"})
    assert answer.status_code == 409 and words in answer.text
    assert recipes.owner is None


def test_another_units_pipeline_is_never_marked_or_read() -> None:
    recipes = _Recipes(_deployed(owning_unit="unit-2"), _GRANT)
    client = _install(recipes)
    assert client.get(_OWNED).status_code == 404
    assert client.put(_OWNED, json={"client_id": "mine"}).status_code == 404
    assert recipes.owner == _GRANT


def test_the_schedule_route_refuses_a_schedule_while_owned_externally() -> None:
    recipes = _Recipes(_deployed(), _GRANT)
    answer = _install(recipes).patch(
        "/v1/investigations/inv-1/ingest/recipes/rcp-1/schedule",
        json={"schedule_cron": "0 6 * * *"},
    )
    assert answer.status_code == 409, answer.text
    assert "owned externally" in answer.text


_QUOTA = "/v1/investigations/inv-1/ingest/recipes/rcp-1/quota"


def _quota_bar(
    principal: Principal, recipe: StudioRecipeDraft | None = None, runs: object = None
) -> Any:
    import asyncio

    quotas = InMemoryQuotaStore()
    asyncio.run(quotas.set(RunQuota(scope="dataset", key="pid", runs_per_day=4)))
    asyncio.run(quotas.set(RunQuota(scope="dataset", key="another", runs_per_day=9)))
    client = _install(_Recipes(recipe or _deployed()))
    app.dependency_overrides[get_run_quotas] = lambda: quotas
    app.dependency_overrides[get_principal] = lambda: principal
    if runs is not None:
        app.dependency_overrides[get_recipe_runs] = lambda: runs
    return client.get(_QUOTA)


def test_the_quota_bar_gives_todays_count_to_a_system_administrator_alone() -> None:
    """The count is every unit's runs into the dataset (rules 3 and 7, the strict reading of the
    independent review of L1.7): `administer_system` reads the number; anyone else, whether the
    quota is used."""
    quota = {"scope": "dataset", "key": "pid", "runs_per_day": 4, "alert_at_share": 0.8}
    admin = APPROVER.model_copy(
        update={"datasets": ["pid"], "roles": [*APPROVER.roles, "right:administer_system"]}
    )
    assert _quota_bar(admin).json() == {"quota": quota, "runs_today": 2, "used": False}
    reader = APPROVER.model_copy(update={"datasets": ["pid"]})
    assert _quota_bar(reader).json() == {"quota": quota, "runs_today": None, "used": False}


def test_a_used_quota_is_told_without_its_count() -> None:
    reader = APPROVER.model_copy(update={"datasets": ["pid"]})
    body = _quota_bar(reader, runs=_RunsToday(4)).json()
    assert body["runs_today"] is None and body["used"] is True


class _RunsToday:
    def __init__(self, today: int) -> None:
        self.today = today

    async def runs_since(self, **_: object) -> int:
        return self.today


@pytest.mark.parametrize(
    ("principal", "recipe", "status"),
    [
        (APPROVER.model_copy(update={"datasets": ["another"]}), None, 422),
        (APPROVER.model_copy(update={"datasets": []}), None, 422),
        (APPROVER.model_copy(update={"datasets": ["pid"]}), _deployed(owning_unit="unit-2"), 404),
    ],
    ids=["a-case-reading-another-dataset", "outside-any-dataset", "another-units-recipe"],
)
def test_the_quota_bar_is_withheld_from_a_case_not_reading_the_dataset(
    principal: Principal, recipe: StudioRecipeDraft | None, status: int
) -> None:
    """Rule 4: the bar reads the recipe's dataset, so only a case that reads it is told (as Test
    and Preview are refused, in the drawer's words), and another unit's recipe is not found."""
    answer = _quota_bar(principal, recipe)
    assert answer.status_code == status, answer.text
    assert "runs_today" not in answer.text and "runs_per_day" not in answer.text
    if status == 422:
        assert "only a case that reads the dataset" in answer.text


@pytest.mark.parametrize(
    "client", ["osprey-conduit", "osprey-glass", "osprey-dashboard-board", "Osprey-Admin"]
)
def test_a_client_the_deployment_registers_is_never_made_an_orchestrator(client: str) -> None:
    """Rule 3: the deployment's own clients (`osprey-*`) have service accounts, and none may be
    handed a pipeline to trigger."""
    recipes = _Recipes(_deployed())
    answer = _install(recipes).put(_OWNED, json={"client_id": client})
    assert answer.status_code == 422, answer.text
    assert "the deployment's own" in answer.text
    assert recipes.owner is None


#: The query parameters each route of L1.7 takes. A dependency annotated with a name defined below
#: its route is read by FastAPI as a query parameter instead (found here: `executor` on
#: `POST /v1/runs`, so every real call answered 422), and this lists none such.
EXPECTED_QUERY = {
    "start_external_run_route": set(),
    "read_external_run": set(),
    "read_pipeline_owned_externally": set(),
    "mark_pipeline_owned_externally": set(),
    "clear_pipeline_owned_externally": set(),
    "read_pipeline_quota": set(),
    "operations_runs": {"days"},
    "set_run_quota": set(),
    "export_dataset_release": {"name", "version"},
    "import_dataset_release": {"dry_run"},
}


def test_each_new_route_takes_only_its_own_query_parameters() -> None:
    from fastapi.routing import APIRoute

    found = {
        r.endpoint.__name__: {p.name for p in r.dependant.query_params}
        | {p.name for d in r.dependant.dependencies for p in d.query_params}
        for r in app.routes
        if isinstance(r, APIRoute) and r.endpoint.__name__ in EXPECTED_QUERY
    }
    assert found == EXPECTED_QUERY
