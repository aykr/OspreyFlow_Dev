"""A drawn dataset (ADR-143 Amendment 2 decisions 3 and 5; ADR-140 Amendment 9 decision 2; L3.1b
step 5): made with its domain model and its home case from a drawing with no case; read through its
home case alone; loaded by no pipeline and judged by no rule until merged.

What a mistake would do, and the case that catches it:

- a drawn dataset that another case can choose, so its drawings reach people its Author never shared
  them with (the orchestrator's access test):
  `test_no_other_case_may_choose_it_and_only_its_home_cases_grantees_read_it`, each check red
  with it alone planted out (`test_each_choice_check_holds_alone`);
- a ceiling above the maker's own clearance:
  `test_its_highest_marking_is_within_the_makers_clearance`;
- a pipeline loading into it, or a rule made in its case: `test_nothing_is_loaded_into_it` and
  `test_no_rule_is_made_in_its_case`, each red with its refusal planted out;
- its model not live, or not its starter pack: `test_making_one_makes_its_model_and_home_case`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from services.api import app as app_module
from services.api.datasets import DRAWN, InMemoryDatasetStore
from services.api.investigations import AccessLevel

from schemas.domain import Principal

from .test_home_cases import PEOPLE, _as, world  # noqa: F401 — `world` is the fixture

JUNIOR = Principal(id="jun-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


class _Rules:
    """The rules store: any rule made is recorded, so a refusal before it shows nothing made."""

    def __init__(self) -> None:
        self.made: list[Any] = []

    def __getattr__(self, name: str) -> Any:
        async def recorded(*args: Any, **kwargs: Any) -> Any:
            self.made.append(name)
            raise AssertionError(f"the rules store was asked to {name}")

        return recorded


@pytest.fixture(autouse=True)
def _a_junior(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> Any:  # noqa: F811
    PEOPLE["junior"] = JUNIOR
    world.rules = _Rules()
    monkeypatch.setattr(app_module.app.state, "typology_rules", world.rules, raising=False)
    monkeypatch.setattr(app_module.app.state, "patterns_store", _Rules(), raising=False)
    yield
    PEOPLE.pop("junior", None)


def _draw(world: SimpleNamespace, person: str = "analyst", **body: Any) -> Any:  # noqa: F811
    fields = {"name": "Smuggling ring", "pack": "niem", "highest_marking": "OFFICIAL", **body}
    return world.client.post("/v1/datasets/drawn", json=fields, headers=_as(person))


def _the_drawn(world: SimpleNamespace) -> Any:  # noqa: F811
    (drawn,) = [d for d in world.datasets.datasets.values() if d.kind == DRAWN]
    return drawn


def test_making_one_makes_its_model_and_home_case(world: SimpleNamespace) -> None:  # noqa: F811
    made = _draw(world)
    assert made.status_code == 201, made.text
    drawn = _the_drawn(world)
    home = made.json()["investigation_id"]
    assert made.json()["dataset_id"] == drawn.id and drawn.highest_marking == "OFFICIAL"
    assert world.datasets.homes[drawn.id].investigation_id == home
    assert world.datasets.cases[home] == [drawn.id]
    assert world.cases.grants[home] == {"ana-1": AccessLevel.AUTHOR}
    assert world.cases.made[home].name == "Smuggling ring"
    import asyncio

    live = asyncio.run(world.models.live(drawn.id))
    assert live is not None and (live.version, set(live.packs)) == (1, {"niem"})
    (entry,) = [e for e in world.audit.entries if e["action"] == "make_drawn_dataset"]
    assert entry["resolved_query"]["highest_marking"] == "OFFICIAL"
    listed = world.client.get("/v1/admin/datasets", headers=_as("admin")).json()
    assert {d["id"]: d["highest_marking"] for d in listed} == {"ds-a": None, drawn.id: "OFFICIAL"}


def test_its_highest_marking_is_within_the_makers_clearance(
    world: SimpleNamespace,  # noqa: F811
) -> None:
    above = _draw(world, "junior", highest_marking="SECRET")
    assert above.status_code == 409, above.text
    assert above.json()["detail"]["error"] == "above_your_clearance"
    unknown = _draw(world, highest_marking="VERY SECRET INDEED")
    assert unknown.status_code == 422
    assert [d for d in world.datasets.datasets.values() if d.kind == DRAWN] == []
    assert world.cases.made.keys() == {"case-a"}


def test_no_other_case_may_choose_it_and_only_its_home_cases_grantees_read_it(
    world: SimpleNamespace,  # noqa: F811
) -> None:
    home = _draw(world).json()["investigation_id"]
    drawn = _the_drawn(world)
    # Not offered to choose, and refused when named.
    offered = world.client.get("/v1/datasets", headers=_as("analyst")).json()
    assert drawn.id not in [d["id"] for d in offered]
    second = world.client.post(
        "/v1/investigations", json={"name": "Another", "dataset_ids": [drawn.id]},
        headers=_as("analyst"),
    )  # fmt: skip
    assert second.status_code == 422, second.text
    assert [c for c, ids in world.datasets.cases.items() if drawn.id in ids] == [home]
    # Read through its home case, by its grantees alone.
    assert world.client.get(f"/v1/investigations/{home}", headers=_as("analyst")).status_code == 200
    stranger = world.client.get(f"/v1/investigations/{home}", headers=_as("engineer"))
    assert stranger.status_code == 404
    world.cases.grants[home]["eng-1"] = AccessLevel.VIEWER  # the Author shares it
    shared = world.client.get(f"/v1/investigations/{home}", headers=_as("engineer"))
    assert shared.status_code == 200


@pytest.mark.parametrize(
    ("widened", "chosen"),
    [(("_choosable",), False), (("list_for",), False), (("_choosable", "list_for"), True)],
    ids=["the-store-alone", "the-list-alone", "both-removed"],
)
def test_each_choice_check_holds_alone(
    world: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    widened: tuple[str, ...],
    chosen: bool,
) -> None:
    """Rule 15: the route takes only a dataset in the reader's list, and the store chooses no drawn
    dataset for a case. Each holds alone; with both planted out, as before drawn datasets, a
    second case reads the drawing."""
    _draw(world)
    drawn = _the_drawn(world)
    real_choosable, real_list = InMemoryDatasetStore._choosable, InMemoryDatasetStore.list_for

    def any_kind(self: Any, dataset_id: str, unit: str, *, kinds: Any) -> Any:
        return real_choosable(self, dataset_id, unit, kinds=(*kinds, DRAWN))

    async def every_one(self: Any, reader: Any) -> Any:
        return [*await real_list(self, reader), drawn]

    if "_choosable" in widened:
        monkeypatch.setattr(InMemoryDatasetStore, "_choosable", any_kind)
    if "list_for" in widened:
        monkeypatch.setattr(InMemoryDatasetStore, "list_for", every_one)
    second = world.client.post(
        "/v1/investigations", json={"name": "Another", "dataset_ids": [drawn.id]},
        headers=_as("analyst"),
    )  # fmt: skip
    readers = [c for c, ids in world.datasets.cases.items() if drawn.id in ids]
    assert (second.status_code == 201, len(readers) > 1) == (chosen, chosen), second.text


def test_nothing_is_loaded_into_it(world: SimpleNamespace) -> None:  # noqa: F811
    """A Studio route of the dataset that loads refuses, in words, before anything is read."""
    _draw(world)
    drawn = _the_drawn(world)
    loading = world.client.post(f"/v1/datasets/{drawn.id}/sources", json={}, headers=_as("analyst"))
    assert loading.status_code == 409, loading.text
    assert loading.json()["error"] == "drawn_not_loaded"


def test_the_loading_refusal_fails_planted_out(
    world: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15, red: with the Studio's refusal planted out, the route goes on past it."""

    async def allowed(*_args: Any, **_kwargs: Any) -> None:
        return None

    app_module.app.dependency_overrides[app_module.refuse_loading_a_composite] = allowed
    try:
        _draw(world)
        drawn = _the_drawn(world)
        answer = world.client.post(
            f"/v1/datasets/{drawn.id}/sources", json={}, headers=_as("analyst")
        )
        assert answer.status_code != 409 or answer.json().get("error") != "drawn_not_loaded"
    finally:
        app_module.app.dependency_overrides.pop(app_module.refuse_loading_a_composite, None)


def test_no_rule_is_made_in_its_case(world: SimpleNamespace) -> None:  # noqa: F811
    home = _draw(world).json()["investigation_id"]
    for path in ("rules", "rules/sentence"):
        answer = world.client.post(
            f"/v1/investigations/{home}/{path}", json={}, headers=_as("analyst")
        )
        assert answer.status_code == 409, (path, answer.text)
        assert answer.json()["error"] == "drawn_not_judged"
    # A working case of another dataset goes on as ever, to the body's own refusal here.
    other = world.client.post("/v1/investigations/case-a/rules", json={}, headers=_as("analyst"))
    assert other.status_code == 422, other.text
    assert world.rules.made == []


def test_the_rule_refusal_fails_planted_out(world: SimpleNamespace) -> None:  # noqa: F811
    """Rule 15, red: the refusal planted out, the rule routes go on to the body's own check."""

    async def allowed(*_args: Any, **_kwargs: Any) -> None:
        return None

    home = _draw(world).json()["investigation_id"]
    for dependency in (
        app_module.refuse_rules_in_a_drawn_case_as_author,
        app_module.refuse_rules_in_a_drawn_case_as_editor,
    ):
        app_module.app.dependency_overrides[dependency] = allowed
    try:
        answer = world.client.post(
            f"/v1/investigations/{home}/rules", json={}, headers=_as("analyst")
        )
        assert answer.status_code == 422, answer.text  # past the refusal, to the body's check
    finally:
        app_module.app.dependency_overrides.clear()
