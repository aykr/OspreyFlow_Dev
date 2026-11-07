"""A composite is read-only for now (ADR-099 Amendment 15): the writes the final L3.1 review found
still reaching past the refusal, each refused up front, and each check's own red companion, which
removes only that check and shows the write it holds back then goes ahead.

- the scheduler (`app._schedule_executor`'s `check_case`): a schedule's run, by *Run now* or by its
  slot, in a case reading a composite, refused in words before `run_recipe_as` is called, for a
  case switched to a composite after its schedule was set too;
- the Admin area's *Run now*, *Change schedule* and *Resume* (`/v1/admin/schedules/...`): 409
  before anything is run, re-timed or resumed;
- the site's grid (`sites/{site}/grid`): 409 before the grid is stored or a cell loaded;
- held rows' rejection (`held-rows/reject`), with the case's loading routes;
- the loading dependency itself, shown holding on two routes (`ingest/recipes/{recipe}/schedule`,
  `ingest/source-files`), each going on to its own write once it alone is removed, and on every
  loading route the Studio and the case have (`test_every_loading_route_carries_the_refusal`);
- corrections' last word (`DatasetStampingGraph.supersede_node`): under no case (the Studio's
  scope), a composite's id still refused; in a composite case, an element the case cannot see
  refused in the same words, and one wholly in the layer corrected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api import app as app_module
from services.api.dataset_scope import (
    CompositeReadOnlyError,
    DatasetStampingGraph,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.scheduler import ScheduleRunRefused

from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal, ProvenanceState, Subgraph
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus

from .test_composite_read_only import _member_node, _NodeGraph, _write
from .working_set.fakes import FakeGraphPort

MEMBER, OTHER, BOTH = "member", "other-member", "both"
WORDS = "do this in a case that reads that dataset"
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
#: Every right a route here asks for, so each is stopped by the refusal alone.
OWNER = Principal(
    id="owner-1", clearance="OFFICIAL", org_unit="unit-1",
    roles=["osprey-admin", "analyst", "data_engineer", "source_author", "source_approver",
           "loader"],
)  # fmt: skip


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


class _Stop(Exception):
    """A route's own work reached, once the refusal is removed: where a companion stops it."""


def _dataset(dataset_id: str, **kind: object) -> Dataset:
    return Dataset(
        id=dataset_id, name=f"{dataset_id} data", owning_unit="unit-1",
        created_at=datetime(2026, 11, 1, tzinfo=UTC), created_by="seed", **kind,  # type: ignore[arg-type]
    )  # fmt: skip


def _store() -> InMemoryDatasetStore:
    store = InMemoryDatasetStore()
    store.add(_dataset(MEMBER))
    store.add(_dataset(OTHER))
    store.add(_dataset(BOTH, kind=COMPOSITE, members=[MEMBER, OTHER]))
    return store


def _recipe(case: str, **more: Any) -> StudioRecipeDraft:
    return StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id="r-1", version=1, status=StudioRecipeStatus.PUBLISHED, label="Feed r-1",
        handling={"classification": "OFFICIAL", "handling_code": "P", "owning_unit": "unit-1",
                  "originator": "unit-1"},
        owning_unit="unit-1", created_by="author-1", created_at=NOW, ready_for_profile=True,
        schedule_cron="0 6 * * 1-5", schedule_timezone="Europe/London", schedule_owner=OWNER.id,
        schedule_set_at=NOW, schedule_case=case, **more,
    )  # fmt: skip


# --- the scheduler ------------------------------------------------------------------------------


class _Investigations:
    async def get_authorized(self, case: str, principal: Principal, *, need: Any) -> object:
        return object()


class _Resolver:
    async def resolve_for_owner_detailed(self, owner_id: str) -> Principal:
        return OWNER


class _Valkey:
    async def set(self, *args: Any, **kwargs: Any) -> bool:
        return True

    async def get(self, key: str) -> None:
        return None

    async def delete(self, *args: Any) -> int:
        return 1


async def _run_now(monkeypatch: pytest.MonkeyPatch, *, switched: bool = False) -> list[Any]:
    """*Run now* through the executor the Conduit builds, `run_recipe_as` a recorder. `switched`:
    the case read a source when its schedule was set, and a composite now."""
    store = _store()
    await store.set_for_case("case-1", [MEMBER], OWNER, case_name="Case")
    if switched:
        await store.set_for_case("case-1", [BOTH], OWNER, case_name="Case")
    else:
        await store.set_for_case("case-2", [BOTH], OWNER, case_name="Both")
    runs: list[Any] = []

    async def run_recipe_as(*args: Any, **kwargs: Any) -> object:
        runs.append(kwargs["investigation_id"])
        return object()

    monkeypatch.setattr(app_module, "run_recipe_as", run_recipe_as)
    monkeypatch.setattr(app_module.RecipeRunDeps, "from_state", staticmethod(lambda s: object()))
    state = SimpleNamespace(
        investigations=_Investigations(), datasets=store, studio_recipes=None, recipe_runs=None,
        valkey=_Valkey(), handling_scheme=load_uk_le_scheme(), principal_resolver=_Resolver(),
        sources=None, alerts_store=None,
    )  # fmt: skip
    executor = app_module._schedule_executor(SimpleNamespace(state=state))  # type: ignore[arg-type]  # noqa: SLF001
    await executor.run_now(_recipe("case-1" if switched else "case-2"))
    return runs


@pytest.mark.parametrize("switched", [False, True], ids=["composite", "switched-to-composite"])
async def test_a_schedule_is_not_run_in_a_composite_case(
    monkeypatch: pytest.MonkeyPatch, switched: bool
) -> None:
    with pytest.raises(ScheduleRunRefused, match="read-only for now") as refused:
        await _run_now(monkeypatch, switched=switched)
    assert "run it in a case that reads that dataset" in str(refused.value)


async def test_the_scheduler_check_fails_with_it_alone_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def allowed() -> None:
        return None

    monkeypatch.setattr(app_module, "refuse_in_a_composite_case", allowed)
    assert await _run_now(monkeypatch) == ["case-2"]


async def _executor_over(store: InMemoryDatasetStore, cases: dict[str, Any]) -> Any:
    """The executor the Conduit builds (`app._schedule_executor`), over `store` and an
    investigation store listing `cases` as the owner's, Editor on each."""
    from services.api.investigations import AccessLevel

    class _Listing(_Investigations):
        async def list_for(self, principal: Principal) -> list[Any]:
            return [(SimpleNamespace(id=c), AccessLevel.EDITOR) for c in cases]

    state = SimpleNamespace(
        investigations=_Listing(), datasets=store, studio_recipes=None, recipe_runs=None,
        valkey=_Valkey(), handling_scheme=load_uk_le_scheme(), principal_resolver=_Resolver(),
        sources=None, alerts_store=None,
    )  # fmt: skip
    return app_module._schedule_executor(SimpleNamespace(state=state))  # type: ignore[arg-type]  # noqa: SLF001


async def test_a_lasting_composite_refusal_is_about_the_schedule_and_pauses_it() -> None:
    """Refused at every slot, so it counts toward the pause after three in a row (ADR-110
    Amendment 3) rather than telling the owner at every slot for ever."""
    from services.api.scheduler import _Refused

    store = _store()
    await store.set_for_case("case-2", [BOTH], OWNER, case_name="Both")
    executor = await _executor_over(store, {"case-2": None})
    with pytest.raises(_Refused) as refused:
        await executor._owner(_recipe("case-2"))  # noqa: SLF001
    assert refused.value.about_the_owner and "read-only for now" in str(refused.value)


async def test_a_source_refresh_falls_back_to_a_case_that_loads_into_its_dataset() -> None:
    """ADR-110 Amendment 6 point 6: the pipeline's own case reads a composite, so another case of
    the owner's that loads into the source's dataset runs the refresh."""
    store = _store()
    await store.set_for_case("case-2", [BOTH], OWNER, case_name="Both")
    await store.set_for_case("case-1", [MEMBER], OWNER, case_name="Member")
    executor = await _executor_over(store, {"case-2": None, "case-1": None})
    assert await executor._case_into(OWNER.id, "case-2", MEMBER) == "case-1"  # noqa: SLF001


# --- the Admin area's schedule routes -----------------------------------------------------------


class _AdminRecipes:
    def __init__(self, recipe: StudioRecipeDraft) -> None:
        self.recipe = recipe
        self.done: list[str] = []

    async def scheduled(self) -> list[StudioRecipeDraft]:
        return [self.recipe]

    async def retime(self, recipe_id: str, **kwargs: Any) -> None:
        self.done.append("retimed")

    async def set_paused(self, recipe_id: str, *, paused: bool, reason: str | None) -> None:
        self.done.append("resumed" if not paused else "paused")


class _AdminExecutor:
    def __init__(self, recipes: _AdminRecipes) -> None:
        self.recipes = recipes

    async def run_now(self, recipe: StudioRecipeDraft) -> None:
        self.recipes.done.append("ran")


class _Audit:
    async def record(self, **kwargs: Any) -> None:
        return None


class _Runs:
    async def for_recipe(self, recipe_id: str, *, limit: int = 50) -> list[Any]:
        return []


ADMIN_ROUTES = [
    ("POST", "/v1/admin/schedules/r-1/run", None, "ran"),
    ("PUT", "/v1/admin/schedules/r-1", {"cron": "0 7 * * 1-5"}, "retimed"),
    ("POST", "/v1/admin/schedules/r-1/resume", None, "resumed"),
]


async def _admin(
    method: str, path: str, body: Any, *, target: str = "case"
) -> tuple[Any, list[str]]:
    from fastapi.testclient import TestClient

    store = _store()
    await store.set_for_case("case-2", [BOTH], OWNER, case_name="Both")
    await store.set_for_case("case-1", [MEMBER], OWNER, case_name="Source")
    recipe = _recipe("case-2") if target == "case" else _recipe("case-1", dataset_id=BOTH)
    recipes = _AdminRecipes(recipe)
    overrides = {
        app_module.get_principal: lambda: OWNER,
        app_module.get_studio_recipes: lambda: recipes,
        app_module.get_schedule_executor: lambda: _AdminExecutor(recipes),
        app_module.get_recipe_runs: lambda: _Runs(),
        app_module.get_audit: _Audit,
        app_module.get_handling_scheme: load_uk_le_scheme,
        app_module.get_datasets: lambda: store,
        app_module.get_recipes_repo_root: lambda: "/nonexistent",
    }
    app_module.app.dependency_overrides.update(overrides)
    try:
        answer = TestClient(app_module.app).request(method, path, json=body)
    finally:
        app_module.app.dependency_overrides.clear()
    return answer, recipes.done


@pytest.mark.parametrize("target", ["case", "dataset"])
@pytest.mark.parametrize(("method", "path", "body", "_done"), ADMIN_ROUTES)
async def test_the_admin_area_neither_runs_retimes_nor_resumes_a_composites_schedule(
    method: str, path: str, body: Any, _done: str, target: str
) -> None:
    answer, done = await _admin(method, path, body, target=target)
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "composite_read_only"
    assert "This is the composite “both data”" in answer.json()["detail"]
    assert done == []


@pytest.mark.parametrize(("method", "path", "body", "done_word"), ADMIN_ROUTES)
async def test_the_admin_check_fails_with_it_alone_removed(
    method: str, path: str, body: Any, done_word: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def allowed(*args: Any) -> None:
        return None

    monkeypatch.setattr(app_module, "_refuse_a_composite_schedule", allowed)
    _answer, done = await _admin(method, path, body)
    assert done_word in done


# --- the case's routes: a site's grid, held rows, a schedule, an upload ------------------------


class _Sites:
    def __init__(self) -> None:
        self.gridded: list[str] = []

    async def get_authorized(self, site_id: str, principal: Principal) -> Any:
        from services.api.sites import Site

        point = {"px": 0, "py": 0, "lon": 0.0, "lat": 0.0}
        return Site.model_validate({
            "id": site_id, "investigation_id": "case-1", "owning_unit": "unit-1",
            "created_at": NOW, "created_by": OWNER.id, "label": "Site", "image_object_key": "k",
            "image_width_px": 10, "image_height_px": 10, "control_points": [point] * 4,
        })  # fmt: skip

    async def set_grid(self, site_id: str, *args: Any, **kwargs: Any) -> Any:
        self.gridded.append(site_id)
        raise _Stop


class _HeldRows:
    def __init__(self) -> None:
        self.decided: list[Any] = []

    async def decide_for_reader(self, ids: Any, *args: Any, **kwargs: Any) -> list[Any]:
        self.decided.extend(ids)
        raise _Stop


class _Recipes:
    def __init__(self) -> None:
        self.scheduled: list[str] = []

    async def update_schedule(self, recipe_id: str, *args: Any, **kwargs: Any) -> Any:
        self.scheduled.append(recipe_id)
        raise _Stop


async def _case_route(
    method: str,
    path: str,
    *,
    body: Any = None,
    content: bytes | None = None,
    without_the_dependency: bool = False,
) -> tuple[Any, dict[str, list[Any]]]:
    """`path` under a case reading the composite, through the real `get_principal`, so the case is
    in scope as in a deployment; each store a recorder that stops the route where it writes."""
    from fastapi.testclient import TestClient

    from .test_analyst_layer import _Investigations as Investigations

    store = _store()
    investigations = Investigations()
    case = await investigations.create(OWNER, name="Both")
    await store.set_for_case(case.id, [BOTH], OWNER, case_name="Both")
    sites, held, recipes = _Sites(), _HeldRows(), _Recipes()
    saved = {k: getattr(app_module.app.state, k, None)
             for k in ("principal_resolver", "datasets", "investigations")}  # fmt: skip
    app_module.app.state.principal_resolver = SimpleNamespace(resolve=lambda token: OWNER)
    app_module.app.state.datasets = store
    app_module.app.state.investigations = investigations
    recipe = _recipe(case.id)
    graph = stamping(FakeGraphPort(Subgraph(nodes=[], edges=[])), registry=store)
    app_module.app.dependency_overrides.update({
        app_module.get_investigations: lambda: investigations,
        app_module.get_audit: _Audit,
        app_module.get_graph: lambda: graph,
        app_module.get_sites: lambda: sites,
        app_module.get_ontology: lambda: object(),
        app_module.get_analytics: lambda: object(),
        app_module.get_held_rows: lambda: held,
        app_module.get_studio_recipes: lambda: recipes,
        app_module.get_authorized_studio_recipe: lambda: recipe,
        app_module.get_recipes_repo_root: lambda: "/nonexistent",
    })  # fmt: skip
    if without_the_dependency:
        _without_the_loading_dependency()
    try:
        http = TestClient(app_module.app, headers={"Authorization": "Bearer token"})
        try:
            answer = http.request(method, path.format(case=case.id), json=body, content=content)
        except _Stop:
            answer = None
    finally:
        app_module.app.dependency_overrides.clear()
        for key, value in saved.items():
            setattr(app_module.app.state, key, value)
    return answer, {"grid": sites.gridded, "held": held.decided, "schedule": recipes.scheduled}


async def test_a_sites_grid_is_not_drawn_in_a_composite_case() -> None:
    answer, wrote = await _case_route(
        "POST", "/v1/investigations/{case}/sites/s-1/grid", body={"rows": 2, "cols": 2}
    )
    assert answer is not None and answer.status_code == 409, answer and answer.text
    assert WORDS in answer.json()["detail"]
    assert wrote["grid"] == []


async def test_the_grid_check_fails_with_it_alone_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allowed() -> None:
        return None

    monkeypatch.setattr(app_module, "refuse_in_a_composite_case", allowed)
    _answer, wrote = await _case_route(
        "POST", "/v1/investigations/{case}/sites/s-1/grid", body={"rows": 2, "cols": 2}
    )
    assert wrote["grid"] == ["s-1"]


#: Each route that the loading dependency alone holds, and the write it holds back.
DEPENDENCY_ROUTES = [
    ("/v1/investigations/{case}/held-rows/reject", {"ids": ["h-1"], "reason": "No"}, "held"),
    ("/v1/investigations/{case}/ingest/recipes/r-1/schedule", {"schedule_cron": None}, "schedule"),
]


@pytest.mark.parametrize(("path", "body", "_kind"), DEPENDENCY_ROUTES)
async def test_held_rows_are_not_rejected_nor_a_schedule_set_in_a_composite_case(
    path: str, body: Any, _kind: str
) -> None:
    method = "PATCH" if path.endswith("/schedule") else "POST"
    answer, wrote = await _case_route(method, path, body=body)
    assert answer is not None and answer.status_code == 409, answer and answer.text
    assert answer.json()["error"] == "composite_read_only"
    assert wrote == {"grid": [], "held": [], "schedule": []}


def _without_the_loading_dependency() -> None:
    async def allowed() -> None:
        return None

    app_module.app.dependency_overrides[app_module.refuse_loading_in_a_composite_case] = allowed


@pytest.mark.parametrize(("path", "body", "kind"), DEPENDENCY_ROUTES)
async def test_the_loading_dependency_alone_holds_each_route(
    path: str, body: Any, kind: str
) -> None:
    """With only the route's dependency removed, the route goes on to its own write: the
    recorder is reached, so the dependency is what held it."""
    method = "PATCH" if path.endswith("/schedule") else "POST"
    _answer, wrote = await _case_route(method, path, body=body, without_the_dependency=True)
    assert wrote[kind], wrote


async def test_an_upload_is_refused_and_with_the_dependency_alone_removed_is_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[str] = []

    async def save_upload(root: Any, name: str, *args: Any, **kwargs: Any) -> Any:
        saved.append(name)
        raise _Stop

    monkeypatch.setattr(app_module, "save_upload", save_upload)
    path = "/v1/investigations/{case}/ingest/source-files?name=rows.csv"
    answer, _ = await _case_route("POST", path, content=b"a,b\n1,2\n")
    assert answer is not None and answer.status_code == 409, answer and answer.text
    assert saved == []
    await _case_route("POST", path, content=b"a,b\n1,2\n", without_the_dependency=True)
    assert saved == ["rows.csv"]


#: Where the case's and the Studio's loading routes live: every route that writes under these
#: carries the refusal, found by walking the app, so a new one fails here until it does or is named
#: below with its reason.
LOADING_PREFIXES = (
    "/v1/investigations/{investigation_id}/ingest/",
    "/v1/datasets/{dataset_id}/",
)
#: Also loading, outside those prefixes: an uploaded document, held rows' rejection.
LOADING_ELSEWHERE = {
    "/v1/investigations/{investigation_id}/documents",
    "/v1/investigations/{investigation_id}/held-rows/reject",
}
#: Under the prefixes but not refused by the route, each for a reason.
NOT_BY_THE_ROUTE = {
    # Dry runs, writing nothing (`verify`'s docstring; the two previews).
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/verify",
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/preview-graph",
    "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/map/handling-preview",
    # Refused by `review.accept_candidate` and `reject_candidate` after their own read, so a
    # finding the reader cannot see answers 404 (`test_composite_read_only.py`).
    "/v1/investigations/{investigation_id}/ingest/candidates/{candidate_id}/accept",
    "/v1/investigations/{investigation_id}/ingest/candidates/{candidate_id}/reject",
}
_WRITES = {"POST", "PUT", "PATCH", "DELETE"}


def _refusals(route: Any) -> list[Any]:
    calls = {app_module.refuse_loading_in_a_composite_case, app_module.refuse_loading_a_composite}
    return [d.dependency for d in getattr(route, "dependencies", []) if d.dependency in calls]


def _loading_routes_without_the_refusal() -> list[str]:
    missing = []
    for route in app_module.app.routes:
        path = getattr(route, "path", "")
        if not (getattr(route, "methods", None) or set()) & _WRITES:
            continue
        loading = path.startswith(LOADING_PREFIXES) or path in LOADING_ELSEWHERE
        if loading and path not in NOT_BY_THE_ROUTE and not _refusals(route):
            missing.append(path)
    return missing


def test_every_loading_route_carries_the_refusal() -> None:
    assert _loading_routes_without_the_refusal() == []
    # And the walk finds what it should: more than the handful named in this file.
    found = [
        r for r in app_module.app.routes
        if getattr(r, "path", "").startswith(LOADING_PREFIXES) and _refusals(r)
    ]  # fmt: skip
    assert len(found) >= 18


@pytest.mark.parametrize(
    "path",
    [
        "/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/publish",
        "/v1/datasets/{dataset_id}/sources/{source_id}/governance",
        "/v1/investigations/{investigation_id}/held-rows/reject",
    ],
)
def test_the_route_census_fails_with_one_refusal_removed(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (route,) = [r for r in app_module.app.routes if getattr(r, "path", None) == path]
    kept = [d for d in route.dependencies if d.dependency not in set(_refusals(route))]
    monkeypatch.setattr(route, "dependencies", kept)
    assert _loading_routes_without_the_refusal() == [path]


# --- corrections' last word -------------------------------------------------------------------


async def test_a_correction_into_a_composite_under_no_case_is_refused() -> None:
    """The Studio reaches a dataset with no case (`scope_to_dataset`): a correction made there is
    asked of the registry like any write."""
    store = _store()
    graph = _NodeGraph(_member_node(ProvenanceState.INFERRED))
    set_case_datasets([BOTH])  # as `scope_to_dataset` leaves it, with no case's scope
    with pytest.raises(CompositeReadOnlyError, match="This is a composite"):
        await stamping(graph, registry=store).supersede_node("p1", _write("p1-next"), "tx")
    assert graph.superseded == []


async def test_the_no_case_correction_check_fails_with_it_alone_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def none(self: Any, dataset_ids: Any) -> set[str]:
        return set()

    monkeypatch.setattr(InMemoryDatasetStore, "composites_among", none)
    graph = _NodeGraph(_member_node(ProvenanceState.INFERRED))
    set_case_datasets([BOTH])
    await stamping(graph, registry=_store()).supersede_node("p1", _write("p1-next"), "tx")
    assert graph.superseded == ["p1"]


async def _in_the_composite_case() -> tuple[InMemoryDatasetStore, str]:
    store = _store()
    await store.set_for_case("case-1", [BOTH], OWNER, case_name="Both")
    layer = await store.ensure_layer("case-1", unit="unit-1", created_by=OWNER.id)
    await scope_to_case(OWNER, "case-1", store)
    return store, layer


async def test_a_correction_the_case_cannot_see_is_refused_in_the_same_words() -> None:
    store, _layer = await _in_the_composite_case()
    graph = _NodeGraph()
    graph._hidden_node_ids = {"hidden"}  # noqa: SLF001 (a node this case may not see)
    with pytest.raises(CompositeReadOnlyError, match=WORDS):
        await stamping(graph, registry=store).supersede_node("hidden", _write("h-next"), "tx")
    assert graph.superseded == []


async def test_the_unseen_correction_check_fails_with_it_alone_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before, an element the case could not read was judged by nothing and went ahead."""
    from services.api import dataset_scope

    store, _layer = await _in_the_composite_case()

    async def allowed() -> None:
        return None

    monkeypatch.setattr(dataset_scope, "refuse_in_a_composite_case", allowed)
    graph = _NodeGraph()
    graph._hidden_node_ids = {"hidden"}  # noqa: SLF001
    await stamping(graph, registry=store).supersede_node("hidden", _write("h-next"), "tx")
    assert graph.superseded == ["hidden"]


async def test_a_correction_wholly_in_the_layer_goes_ahead() -> None:
    store, layer = await _in_the_composite_case()
    mine = _member_node(ProvenanceState.INFERRED, "mine").model_copy(update={"datasets": [layer]})
    graph = _NodeGraph(mine)
    await stamping(graph, registry=store).supersede_node("mine", _write("mine-next"), "tx")
    assert graph.superseded == ["mine"]


async def test_supersede_nodes_last_word_fails_with_it_alone_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The last word alone, at the stamping graph's own call (no service in front of it)."""

    async def allowed(self: Any, datasets: Any) -> None:
        return None

    monkeypatch.setattr(DatasetStampingGraph, "_refuse_into_a_composite", allowed)
    store, _layer = await _in_the_composite_case()
    graph = _NodeGraph(_member_node(ProvenanceState.INFERRED))
    await stamping(graph, registry=store).supersede_node("p1", _write("p1-next"), "tx")
    assert graph.superseded == ["p1"]
