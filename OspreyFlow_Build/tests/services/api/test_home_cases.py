"""A dataset's home case and *Make live*'s owner step (ADR-145 Amendment 4 decisions 2, 4 and 7;
ADR-140 Amendment 9 decision 5; L3.1b step 4). The real app and `get_principal` run, so the
dataset's gate and the case's level checks are what is tested; the stores are stand-ins that
refuse what the real ones refuse.

What a mistake would do, and the case that catches it:

- a dataset made live with no one answering for it: `test_the_first_make_live_needs_its_owners`;
- a service account, or an account the directory cannot vouch for, named as an owner:
  `test_only_a_person_may_answer_for_a_dataset`, and with no directory at all,
  `test_with_no_directory_the_owners_cannot_be_checked_so_nothing_goes_live`;
- an owner kind Admin › System forbids, or a team before teams exist:
  `test_the_system_setting_and_teams_refuse_in_words`;
- the owners not becoming the home case's Authors, or the maker kept as one when not named:
  `test_the_owners_become_the_home_cases_authors_and_the_maker_does_not_stay_one`, red with the
  maker's grant left (`test_the_authors_check_fails_with_the_makers_grant_left`);
- a second home case at a later *Make live*, or owners asked again:
  `test_a_later_make_live_asks_nothing_and_makes_no_second_home_case`;
- a home case removed while its dataset exists: `test_a_home_case_cannot_be_removed`;
- the System setting changed by anyone but an administrator, or unaudited:
  `test_the_owner_setting_is_an_administrators_and_audited`.
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
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.target_models import CORE_TYPES_FOR_TESTS, InMemoryTargetModelStore

from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal

PEOPLE = {
    name: Principal(id=pid, clearance="SECRET", org_unit="unit-1", roles=roles)
    for name, pid, roles in (
        ("engineer", "eng-1", ["data_engineer"]),
        ("admin", "adm-1", ["osprey-admin"]),
        ("analyst", "ana-1", ["analyst"]),
    )
}
PERSONS = {"eng-1", "ana-1", "per-2", "adm-1"}  # what the directory holds as people
ROBOT = "service-account-loader"


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Names:
    """The directory: who is a person; `None` with no directory (`people` as the real one)."""

    def __init__(self, persons: set[str] | None) -> None:
        self.persons = persons

    async def people(self, ids: Any) -> set[str] | None:
        return None if self.persons is None else {i for i in ids if i in self.persons}

    async def display_names(self, ids: Any) -> dict[str, str]:
        return {}


class _Cases:
    """Cases and their grants: a level is held only by a grant, as the real store holds it."""

    def __init__(self) -> None:
        self.made: dict[str, Investigation] = {}
        self.grants: dict[str, dict[str, AccessLevel]] = {}
        self.removed: list[str] = []

    def seed(self, case_id: str, name: str, grants: dict[str, AccessLevel]) -> None:
        self.made[case_id] = Investigation(
            id=case_id, name=name, created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="seed", owning_unit="unit-1",
        )  # fmt: skip
        self.grants[case_id] = dict(grants)

    async def create(self, principal: Principal, *, name: str, **_: Any) -> Investigation:
        case_id = f"home-{len(self.made)}"
        self.seed(case_id, name, {principal.id: AccessLevel.AUTHOR})
        return self.made[case_id]

    async def set_grant(self, case_id: str, account: str, level: AccessLevel, *, by: Any) -> None:
        self.grants[case_id][account] = level

    async def remove_grant(self, case_id: str, account: str, *, by: Any) -> None:
        self.grants[case_id].pop(account, None)

    async def get_authorized(
        self, case_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        held = self.grants.get(case_id, {}).get(principal.id)
        if case_id not in self.made or case_id in self.removed or held is None:
            raise InvestigationNotFoundError(case_id)
        order = [AccessLevel.VIEWER, AccessLevel.EDITOR, AccessLevel.AUTHOR]
        if order.index(held) < order.index(need):
            raise InsufficientAccessError(case_id)
        return self.made[case_id]

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return [
            (self.made[c], g[principal.id])
            for c, g in self.grants.items()
            if principal.id in g and c not in self.removed
        ]

    async def hidden_tab_ids(self, principal: Principal) -> set[str]:
        return set()

    async def remove(self, case_id: str, *, by: Any) -> None:
        self.removed.append(case_id)


class _Recipes:
    async def feeding(self, dataset_ids: Any) -> list[Any]:
        return []

    async def flag_for_model(self, dataset_id: str, flagged: Any) -> list[str]:
        return []

    async def set_paused(self, *args: Any, **kwargs: Any) -> None:
        return None


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    datasets = InMemoryDatasetStore()
    datasets.add(
        Dataset(id="ds-a", name="Prison records", owning_unit="unit-1",
                created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="eng-1")
    )  # fmt: skip
    cases = _Cases()
    # The engineer's working case loads into ds-a, so the dataset's gate lets them in.
    cases.seed("case-a", "Working case", {"eng-1": AccessLevel.AUTHOR, "ana-1": AccessLevel.AUTHOR})
    datasets.cases["case-a"] = ["ds-a"]
    names, audit = _Names(set(PERSONS)), _Audit()
    models = InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS)
    state = {
        "principal_resolver": _Resolver(), "investigations": cases, "datasets": datasets,
        "studio_recipes": _Recipes(), "audit": audit, "target_models": models,
        "principal_names": names, "handling_scheme": load_uk_le_scheme(),
        "ontology": load_deployment_ontology(),
    }  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(
        client=TestClient(app), datasets=datasets, cases=cases, names=names, audit=audit,
        models=models,
    )  # fmt: skip


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


def _make_live(world: SimpleNamespace, owners: Any = None, version: int = 1) -> Any:
    world.client.post("/v1/datasets/ds-a/model/draft", headers=_as("engineer"))
    body: dict[str, Any] = {"version": version}
    if owners is not None:
        body["owners"] = owners
    return world.client.post(
        "/v1/datasets/ds-a/model/make-live", json=body, headers=_as("engineer")
    )


def test_the_first_make_live_needs_its_owners(world: SimpleNamespace) -> None:
    answer = _make_live(world)
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "owner_needed"
    assert "who answers for this dataset?" in answer.json()["detail"]
    assert world.datasets.homes == {}


def test_only_a_person_may_answer_for_a_dataset(world: SimpleNamespace) -> None:
    for owners in ({"people": [ROBOT]}, {"people": ["eng-1", "no-such-account"]}):
        answer = _make_live(world, owners)
        assert answer.status_code == 409, answer.text
        assert "never a service account" in answer.json()["detail"]
        world.client.delete("/v1/datasets/ds-a/model/draft", headers=_as("engineer"))
    assert world.datasets.homes == {}


def test_with_no_directory_the_owners_cannot_be_checked_so_nothing_goes_live(
    world: SimpleNamespace,
) -> None:
    world.names.persons = None
    answer = _make_live(world, {"people": ["eng-1"]})
    assert answer.status_code == 409 and "cannot be checked" in answer.json()["detail"]
    assert world.datasets.homes == {}


@pytest.mark.parametrize(
    ("setting", "owners", "words"),
    [
        ("people_and_teams", {"team": "Prison intel data team"}, "until teams are built"),
        ("people_only", {"team": "Prison intel data team"}, "allows people only"),
        ("teams_only", {"people": ["eng-1"]}, "allows teams only"),
    ],
)
def test_the_system_setting_and_teams_refuse_in_words(
    world: SimpleNamespace, setting: str, owners: Any, words: str
) -> None:
    world.datasets.owners_may_be = setting
    answer = _make_live(world, owners)
    assert answer.status_code == 409 and words in answer.json()["detail"], answer.text
    assert world.datasets.homes == {}


def test_the_owners_become_the_home_cases_authors_and_the_maker_does_not_stay_one(
    world: SimpleNamespace,
) -> None:
    answer = _make_live(world, {"people": ["per-2", "ana-1"]})
    assert answer.status_code == 200, answer.text
    home = world.datasets.homes["ds-a"]
    assert world.cases.made[home.investigation_id].name == "Prison records"
    assert world.cases.grants[home.investigation_id] == {
        "ana-1": AccessLevel.AUTHOR, "per-2": AccessLevel.AUTHOR,
    }  # fmt: skip
    assert world.datasets.cases[home.investigation_id] == ["ds-a"]
    assert home.made_by == "eng-1"
    (made,) = [e for e in world.audit.entries if e["action"] == "make_home_case"]
    assert made["resolved_query"] == {"dataset_id": "ds-a", "owners": ["ana-1", "per-2"]}


def test_the_authors_check_fails_with_the_makers_grant_left(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: the maker's own grant left in place, the maker is an Author of a home case
    they did not name themselves to."""

    async def kept(self: Any, *args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(_Cases, "remove_grant", kept)
    _make_live(world, {"people": ["per-2"]})
    home = world.datasets.homes["ds-a"].investigation_id
    assert "eng-1" in world.cases.grants[home]


def test_a_later_make_live_asks_nothing_and_makes_no_second_home_case(
    world: SimpleNamespace,
) -> None:
    assert _make_live(world, {"people": ["eng-1"]}).status_code == 200
    again = _make_live(world, {"people": ["eng-1"]}, version=2)
    assert again.status_code == 409 and "already has its owners" in again.json()["detail"]
    world.client.delete("/v1/datasets/ds-a/model/draft", headers=_as("engineer"))
    assert _make_live(world, None, version=2).status_code == 200
    assert len(world.datasets.homes) == 1
    assert len([e for e in world.audit.entries if e["action"] == "make_home_case"]) == 1


def test_a_home_case_cannot_be_removed(world: SimpleNamespace) -> None:
    """Removed by its Author, an analyst holding `remove_case`: refused for the home case, while a
    working case reading the same dataset is removed as ever."""
    _make_live(world, {"people": ["ana-1"]})
    home = world.datasets.homes["ds-a"].investigation_id
    refused = world.client.delete(f"/v1/investigations/{home}", headers=_as("analyst"))
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["error"] == "home_case_kept"
    assert home not in world.cases.removed
    working = world.client.delete("/v1/investigations/case-a", headers=_as("analyst"))
    assert working.status_code == 204, working.text


def test_the_owner_setting_is_an_administrators_and_audited(world: SimpleNamespace) -> None:
    path = "/v1/admin/settings/dataset-owners"
    assert world.client.get(path, headers=_as("admin")).json() == {
        "owners_may_be": "people_and_teams"
    }
    refused = world.client.put(path, json={"owners_may_be": "people_only"}, headers=_as("engineer"))
    assert refused.status_code == 403
    changed = world.client.put(path, json={"owners_may_be": "people_only"}, headers=_as("admin"))
    assert changed.status_code == 200 and world.datasets.owners_may_be == "people_only"
    (entry,) = [e for e in world.audit.entries if e["action"] == "set_dataset_owner_setting"]
    assert entry["resolved_query"] == {"before": "people_and_teams", "after": "people_only"}
    assert app_module.app is app
