"""A dataset's domain model routes (`/v1/datasets/{dataset_id}/model`; ADR-140 decisions 4 and 5,
R12; ADR-112 Amendment 6; L3.1b step 1). The real app and the real `get_principal` run, so the
dataset's gate is what is tested, with only the token resolver and the stores standing in.

What a mistake would do, and the case that catches it:

- a person reaching a dataset none of their cases loads into, or another unit's, told anything but
  404 on any model route: `test_every_model_route_is_a_404_for_a_dataset_not_reached`;
- someone without `edit_target_model` changing a model:
  `test_every_model_route_is_refused_without_the_right`;
- a second draft, or making live a draft changed since it was read:
  `test_the_draft_and_make_live_in_order`;
- *Make live* flagging a pipeline it does not affect, or missing one it does, or leaving a flagged
  pipeline's schedule running:
  `test_make_live_flags_and_pauses_exactly_the_pipelines_writing_a_change`;
- the impact naming a case or composite the reader may not open (rule 7):
  `test_the_impact_names_only_cases_and_composites_the_reader_may_open`, red with each filter
  planted out;
- a route on a dataset with no model answering as if it had one: `test_no_model_yet_in_words`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api.app import app
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.target_models import CORE_TYPES_FOR_TESTS, InMemoryTargetModelStore

from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal

PEOPLE = {
    name: Principal(id=pid, clearance="SECRET", org_unit=unit, roles=[role])
    for name, pid, unit, role in (
        ("engineer", "eng-1", "unit-1", "data_engineer"),
        ("analyst", "ana-1", "unit-1", "analyst"),
        ("stranger", "str-1", "unit-2", "data_engineer"),
    )
}
#: The cases each person holds a level in, by the datasets each reads (its first loads into it).
CASES: dict[str, dict[str, list[str]]] = {
    "eng-1": {"case-a": ["ds-a"], "case-c": ["comp-seen"]},
    "ana-1": {"case-n": ["ds-a"]},
    "str-1": {"case-s": ["ds-s"]},
}
#: A case reading ds-a through a composite nobody here holds a level in.
HIDDEN = {"case-hidden": ["comp-hidden"]}

MODEL_ROUTES = [
    ("GET", "/model", None),
    ("POST", "/model/draft", None),
    ("PUT", "/model/draft", {"packs": {}, "extensions": [], "reference_lists": []}),
    ("DELETE", "/model/draft", None),
    ("GET", "/model/impact", None),
    ("POST", "/model/make-live", {"version": 1}),
    ("POST", "/model/revert", {"version": 1}),
]


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Cases:
    async def list_for(self, principal: Principal) -> list[tuple[Any, str]]:
        return [(SimpleNamespace(id=c, name=f"Case {c}"), "editor") for c in CASES[principal.id]]


def _recipe(recipe_id: str, label: str, writes: list[str]) -> Any:
    """A deployed pipeline as `feeding` returns it: what its row template writes is what counts."""
    entities = [SimpleNamespace(type=t) for t in writes if t[0].isupper() and not t.isupper()]
    edges = [SimpleNamespace(type=t) for t in writes if t.isupper()]
    return SimpleNamespace(
        recipe_id=recipe_id,
        label=label,
        row_template=SimpleNamespace(entities=entities, edges=edges),
    )


class _Recipes:
    def __init__(self) -> None:
        self.deployed = [
            _recipe("r-accounts", "Bank accounts", ["Person", "Account", "HOLDS_ACCOUNT"]),
            _recipe("r-people", "People", ["Person", "COMMUNICATED_WITH"]),
        ]
        self.flagged: list[tuple[str, list[tuple[str, str]]]] = []
        self.paused: list[tuple[str, str]] = []

    async def feeding(self, dataset_ids: list[str]) -> list[Any]:
        return list(self.deployed) if dataset_ids == ["ds-a"] else []

    async def flag_for_model(self, dataset_id: str, flagged: list[tuple[str, str]]) -> list[str]:
        self.flagged.append((dataset_id, flagged))
        return [label for label in ("Bank accounts",) if flagged]

    async def set_paused(self, recipe_id: str, *, paused: bool, reason: str | None) -> None:
        assert paused and reason
        self.paused.append((recipe_id, reason))


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


def _dataset(dataset_id: str, unit: str = "unit-1", **kind: Any) -> Dataset:
    return Dataset(
        id=dataset_id, name=f"Dataset {dataset_id}", owning_unit=unit,
        created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="s", **kind,
    )  # fmt: skip


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    datasets = InMemoryDatasetStore()
    for d, unit in (("ds-a", "unit-1"), ("ds-x", "unit-1"), ("ds-s", "unit-2")):
        datasets.add(_dataset(d, unit))
    datasets.add(_dataset("comp-seen", kind=COMPOSITE, members=["ds-a", "ds-x"]))
    datasets.add(_dataset("comp-hidden", kind=COMPOSITE, members=["ds-x", "ds-a"]))
    for person in (*CASES.values(), HIDDEN):
        for case, reads in person.items():
            datasets.cases[case] = reads
    recipes, audit = _Recipes(), _Audit()
    models = InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS)
    state = {
        "principal_resolver": _Resolver(), "investigations": _Cases(), "datasets": datasets,
        "studio_recipes": recipes, "audit": audit, "target_models": models,
        "handling_scheme": load_uk_le_scheme(), "ontology": load_deployment_ontology(),
    }  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(client=TestClient(app), recipes=recipes, audit=audit, models=models)


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


def _call(world: SimpleNamespace, method: str, path: str, body: Any, person: str) -> Any:
    return world.client.request(method, path, json=body, headers=_as(person))


@pytest.mark.parametrize(("method", "path", "body"), MODEL_ROUTES)
def test_every_model_route_is_a_404_for_a_dataset_not_reached(
    world: SimpleNamespace, method: str, path: str, body: Any
) -> None:
    """Another unit's dataset, a missing one, and one the engineer's cases only read through a
    composite, answer alike, and nothing is written (rule 3)."""
    for dataset in ("ds-s", "no-such", "ds-x"):
        answer = _call(world, method, f"/v1/datasets/{dataset}{path}", body, "engineer")
        assert answer.status_code == 404, (dataset, answer.text)
        assert answer.json() == {"detail": "not_found"}
    assert world.audit.entries == [] and world.recipes.flagged == []


@pytest.mark.parametrize(("method", "path", "body"), MODEL_ROUTES)
def test_every_model_route_is_refused_without_the_right(
    world: SimpleNamespace, method: str, path: str, body: Any
) -> None:
    """The analyst reaches ds-a through their case, but holds no `edit_target_model`."""
    answer = _call(world, method, f"/v1/datasets/ds-a{path}", body, "analyst")
    assert answer.status_code == 403, answer.text
    assert world.audit.entries == []


def test_no_model_yet_in_words(world: SimpleNamespace) -> None:
    read = _call(world, "GET", "/v1/datasets/ds-a/model", None, "engineer")
    assert read.status_code == 200 and read.json() == {"live": None, "draft": None}
    for method, path, body in (
        ("GET", "/model/impact", None),
        ("POST", "/model/revert", {"version": 1}),
    ):
        answer = _call(world, method, f"/v1/datasets/ds-a{path}", body, "engineer")
        assert answer.status_code == 409, answer.text
        assert answer.json()["error"] == "no_model_yet"
        assert "no domain model yet" in answer.json()["detail"]


def test_the_draft_and_make_live_in_order(world: SimpleNamespace) -> None:
    opened = _call(world, "POST", "/v1/datasets/ds-a/model/draft", None, "engineer")
    assert opened.status_code == 201 and opened.json()["version"] == 1
    again = _call(world, "POST", "/v1/datasets/ds-a/model/draft", None, "engineer")
    assert again.status_code == 409 and again.json()["error"] == "model_refused"
    assert "already has a draft" in again.json()["detail"]
    stale = _call(world, "POST", "/v1/datasets/ds-a/model/make-live", {"version": 2}, "engineer")
    assert stale.status_code == 409 and "not 2" in stale.json()["detail"]
    live = _call(world, "POST", "/v1/datasets/ds-a/model/make-live", {"version": 1}, "engineer")
    assert live.status_code == 200, live.text
    assert live.json()["live"]["state"] == "live" and live.json()["previous"] is None
    reverted = _call(world, "POST", "/v1/datasets/ds-a/model/revert", {"version": 1}, "engineer")
    assert reverted.status_code == 409  # version 1 is live, not an earlier one
    actions = [e["action"] for e in world.audit.entries]
    assert actions == ["open_model_draft", "make_model_live"]


def test_make_live_flags_and_pauses_exactly_the_pipelines_writing_a_change(
    world: SimpleNamespace,
) -> None:
    """FIBO added: `Account` and `HOLDS_ACCOUNT` change, so the pipeline writing them is flagged
    and paused with the reason, and the one writing only core types is not."""
    _call(world, "POST", "/v1/datasets/ds-a/model/draft", None, "engineer")
    _call(world, "POST", "/v1/datasets/ds-a/model/make-live", {"version": 1}, "engineer")
    assert world.recipes.paused == []  # bare POLE to bare POLE changes nothing
    _call(world, "POST", "/v1/datasets/ds-a/model/draft", None, "engineer")
    fibo = {"packs": {"fibo": 1}, "extensions": [], "reference_lists": []}
    saved = _call(world, "PUT", "/v1/datasets/ds-a/model/draft", fibo, "engineer")
    assert saved.status_code == 200, saved.text
    impact = _call(world, "GET", "/v1/datasets/ds-a/model/impact", None, "engineer").json()
    assert impact["packs_added"] == ["fibo"]
    assert {"Account", "HOLDS_ACCOUNT"} <= set(impact["changed_types"])
    assert "Person" not in impact["changed_types"]
    assert [(p["recipe_id"], p["writes"]) for p in impact["pipelines"]] == [
        ("r-accounts", ["Account", "HOLDS_ACCOUNT"])
    ]
    made = _call(world, "POST", "/v1/datasets/ds-a/model/make-live", {"version": 2}, "engineer")
    assert made.status_code == 200, made.text
    assert [p["recipe_id"] for p in made.json()["flagged"]] == ["r-accounts"]
    ((dataset, flagged),) = world.recipes.flagged[-1:]
    assert dataset == "ds-a" and [r for r, _ in flagged] == ["r-accounts"]
    ((paused, reason),) = world.recipes.paused
    assert paused == "r-accounts" and "Account, HOLDS_ACCOUNT" in reason and "version 2" in reason
    (entry,) = [e for e in world.audit.entries if e["action"] == "make_model_live"][-1:]
    assert entry["resolved_query"]["flagged"] == ["r-accounts"]


def _impact(world: SimpleNamespace) -> dict[str, Any]:
    _call(world, "POST", "/v1/datasets/ds-a/model/draft", None, "engineer")
    answer = _call(world, "GET", "/v1/datasets/ds-a/model/impact", None, "engineer")
    assert answer.status_code == 200, answer.text
    return answer.json()  # type: ignore[no-any-return]


def test_the_impact_names_only_cases_and_composites_the_reader_may_open(
    world: SimpleNamespace,
) -> None:
    """ds-a is read by the engineer's case-a, by case-c through comp-seen, and by case-hidden
    through comp-hidden, which the engineer holds no level in: the last is neither listed, named
    nor counted (rule 7)."""
    impact = _impact(world)
    assert [c["investigation_id"] for c in impact["cases"]] == ["case-a", "case-c"]
    assert impact["composites"] == ["Dataset comp-seen"]
    assert "case-hidden" not in str(impact) and "comp-hidden" not in str(impact)


def test_the_hidden_case_and_composite_are_named_with_the_filters_planted_out(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: `impact_of` handed a reader's case list holding every case, as an unfiltered
    read would be, names the hidden case and its composite."""
    real = app_module.impact_of

    class _Everyone:
        async def list_for(self, principal: Any) -> list[tuple[Any, str]]:
            every = [c for person in (*CASES.values(), HIDDEN) for c in person]
            return [(SimpleNamespace(id=c, name=f"Case {c}"), "editor") for c in every]

    async def unfiltered(*args: Any, **kwargs: Any) -> Any:
        return await real(*args, **{**kwargs, "cases": _Everyone()})

    monkeypatch.setattr(app_module, "impact_of", unfiltered)
    impact = _impact(world)
    assert "case-hidden" in [c["investigation_id"] for c in impact["cases"]]
    assert "Dataset comp-hidden" in impact["composites"]


@pytest.mark.parametrize(("method", "path", "body"), MODEL_ROUTES)
def test_a_composites_model_is_read_not_changed(
    world: SimpleNamespace, method: str, path: str, body: Any
) -> None:
    """A composite is read-only for now, and its own model waits for the superset check over its
    members' (phase 5 item 4): every write refused in words before anything is written, a read
    answered. The engineer reaches comp-seen through case-c, which reads it."""
    answer = _call(world, method, f"/v1/datasets/comp-seen{path}", body, "engineer")
    if method == "GET":
        assert answer.status_code in (200, 409), answer.text  # no model yet, for the impact
        assert answer.json().get("error") != "composite_read_only"
    else:
        assert answer.status_code == 409, answer.text
        assert answer.json()["error"] == "composite_read_only"
        assert world.models._held.get("comp-seen", []) == []  # noqa: SLF001
