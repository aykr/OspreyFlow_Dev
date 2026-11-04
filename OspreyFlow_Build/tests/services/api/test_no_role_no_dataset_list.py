"""No role, no dataset list (`06_DECISIONS.md` ADR-099 Amendment 11; the owner, 4 November 2026).

A person holding no role — no right at all, `rights_for(roles)` empty — reads no dataset's name and
no dataset's id, on any path, even when an administrator has given them a unit (and a case level)
before a role. Found in build order step 20 drop 2 (open question 28): an arrival through the
organisation's sign-in given a unit but no role was shown that unit's dataset list.

**Where the rule lives:** in the dataset store, the one place every dataset's name is read from
(`DatasetStore.list_for` and `DatasetStore.of_case` take the reader, and the reader's having a
right is a condition of the query itself). The paths that need a right already refuse a role-less
principal before any query runs (`require_right`). Every route reachable with no right is in
`test_route_rights.py`'s table as `None`; the four of those that name datasets are here.

What a mistake here would do, and the case that catches it (rule 12):
- the unit's list shown to a role-less person (the finding itself) —
  `test_the_unit_list_is_empty_for_a_person_with_no_role`;
- the list's length telling a role-less person the unit holds datasets (rule 3's existence clause)
  — the same test, against a unit holding none;
- a role the deployment does not know counted as a role — `..._with_only_roles_it_does_not_know`;
- the case picker, a case's own datasets, or the engine choice's reasons naming them, or counting
  them, to a role-less person holding a case level — the three `test_a_case_*` cases;
- the Admin area's list reachable without the right — `test_the_admin_list_is_refused_...`;
- a person with a role losing what they saw — every `..._unchanged_for_*` case, one per role;
- the store answering a role-less reader (the rule's own place, not only the routes) —
  `test_the_store_names_no_dataset_to_a_reader_with_no_role`; its Postgres half is
  `test_datasets_store.py::test_postgres_names_no_dataset_to_a_reader_with_no_role` (live).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_datasets,
    get_investigations,
    get_model_routes,
    get_principal,
)
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import AccessLevel, Investigation, InvestigationNotFoundError
from services.api.model_routing import Engine, ModelRoutes

from schemas.domain import Principal

UNIT = "unit-1"
EMPTY_UNIT = "unit-9"  # holds no dataset


def _person(roles: list[str], unit: str = UNIT, id_: str | None = None) -> Principal:
    return Principal(
        id=id_ or f"person-{'-'.join(roles) or 'no-role'}-{unit}",
        clearance="OFFICIAL",
        org_unit=unit,
        roles=roles,
    )


NO_ROLE = _person([])
NO_ROLE_EMPTY_UNIT = _person([], EMPTY_UNIT)
#: Keycloak's own default roles and anything else this deployment does not know confer nothing.
UNKNOWN_ROLES_ONLY = _person(["default-roles-osprey", "offline_access", "uma_authorization"])
WITH_ROLE = {
    "analyst": _person(["analyst"]),
    "data_engineer": _person(["data_engineer"]),
    "osprey-admin": _person(["osprey-admin"]),
    "reports_viewer": _person(["reports_viewer"]),
    "a-single-right": _person(["right:read_reports"]),
}
ADMIN = WITH_ROLE["osprey-admin"]


def _dataset(id_: str, name: str, unit: str = UNIT) -> Dataset:
    return Dataset(
        id=id_,
        name=name,
        owning_unit=unit,
        created_at=datetime(2026, 11, 4, tzinfo=UTC),
        created_by="seed",
    )


class _Cases:
    """Every person holds Viewer on each case of their own unit — role or none, as an Author may
    grant a level to someone an administrator has not yet given a role."""

    def __init__(self) -> None:
        self.cases = [
            Investigation(
                id=case_id,
                name=f"Case {case_id}",
                created_at=datetime(2026, 11, 4, tzinfo=UTC),
                created_by="author",
                owning_unit=unit,
            )
            for case_id, unit in (("case-two", UNIT), ("case-one", UNIT))
        ]

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        for case in self.cases:
            if case.id == investigation_id and case.owning_unit == principal.org_unit:
                return case
        raise InvestigationNotFoundError(investigation_id)

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return [(c, AccessLevel.VIEWER) for c in self.cases if c.owning_unit == principal.org_unit]

    async def hidden_tab_ids(self, principal: Principal) -> set[str]:
        return set()


class _Audit:
    async def record(self, **kwargs: object) -> None:
        return None


def _routes() -> ModelRoutes:
    """One hosted engine with a key, so a case reading a dataset at `none` is given a reason."""
    gemini = Engine(
        name="gemini",
        label="Gemini",
        models={"extraction": "gemini/gemini-2.5-flash"},
        key_present=True,
    )
    return ModelRoutes(
        locals={"extraction": "qwen2.5:7b-instruct", "vision": None, "transcription": None,
                "embedding": None},
        engines={"gemini": gemini},
        sendable=frozenset({"P"}),
    )  # fmt: skip


@pytest.fixture
def store() -> InMemoryDatasetStore:
    held = InMemoryDatasetStore()
    held.add(_dataset("enron", "Enron corpus"))
    held.add(_dataset("fixture", "Fixture Corp"))
    held.add(_dataset("theirs", "Another unit's", unit="unit-2"))
    held.cases["case-two"] = ["fixture", "enron"]
    held.cases["case-one"] = ["enron"]
    return held


@pytest.fixture
def client(store: InMemoryDatasetStore) -> Any:
    who: dict[str, Principal] = {"principal": NO_ROLE}
    app.dependency_overrides[get_datasets] = lambda: store
    app.dependency_overrides[get_investigations] = _Cases
    app.dependency_overrides[get_audit] = _Audit
    app.dependency_overrides[get_model_routes] = _routes
    app.dependency_overrides[get_principal] = lambda: who["principal"]
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.who = who  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def _as(client: Any, principal: Principal) -> None:
    client.who["principal"] = principal


# --- the rule's own place ------------------------------------------------------------------------


def test_a_reader_reads_dataset_names_only_while_holding_a_right() -> None:
    from services.api.datasets import reads_dataset_names

    assert not reads_dataset_names(NO_ROLE)
    assert not reads_dataset_names(UNKNOWN_ROLES_ONLY)
    for principal in WITH_ROLE.values():
        assert reads_dataset_names(principal), principal.roles


async def test_the_store_names_no_dataset_to_a_reader_with_no_role(
    store: InMemoryDatasetStore,
) -> None:
    for reader in (NO_ROLE, UNKNOWN_ROLES_ONLY):
        assert await store.list_for(reader) == []
        assert await store.of_case("case-two", reader) == []
    analyst = WITH_ROLE["analyst"]
    assert [d.name for d in await store.list_for(analyst)] == ["Enron corpus", "Fixture Corp"]
    assert [d.id for d in await store.of_case("case-two", analyst)] == ["fixture", "enron"]


# --- GET /v1/datasets: the unit's list ------------------------------------------------------------


def test_the_unit_list_is_empty_for_a_person_with_no_role(client: Any) -> None:
    _as(client, NO_ROLE)
    response = client.get("/v1/datasets")
    assert response.status_code == 200, response.text
    assert response.json() == []
    for name in ("Enron", "Fixture", "enron", "fixture"):
        assert name not in response.text
    # Rule 3's existence clause: a unit holding two datasets answers byte for byte as one holding
    # none, so neither the body nor its length says the unit holds any.
    _as(client, NO_ROLE_EMPTY_UNIT)
    empty = client.get("/v1/datasets")
    assert (empty.status_code, empty.content) == (response.status_code, response.content)
    assert empty.headers["content-length"] == response.headers["content-length"]


def test_the_unit_list_is_empty_for_a_person_with_only_roles_it_does_not_know(client: Any) -> None:
    _as(client, UNKNOWN_ROLES_ONLY)
    response = client.get("/v1/datasets")
    assert (response.status_code, response.json()) == (200, [])


@pytest.mark.parametrize("role", sorted(WITH_ROLE))
def test_the_unit_list_is_unchanged_for_a_person_with_a_role(client: Any, role: str) -> None:
    _as(client, WITH_ROLE[role])
    response = client.get("/v1/datasets")
    assert response.status_code == 200, response.text
    assert [(d["id"], d["name"]) for d in response.json()] == [
        ("enron", "Enron corpus"),
        ("fixture", "Fixture Corp"),
    ]


# --- GET /v1/investigations: the case picker -----------------------------------------------------


def test_a_case_listed_to_a_person_with_no_role_names_no_dataset(client: Any) -> None:
    _as(client, NO_ROLE)
    response = client.get("/v1/investigations")
    assert response.status_code == 200, response.text
    listed = {c["id"]: c for c in response.json()}
    assert set(listed) == {"case-two", "case-one"}
    for case in listed.values():
        assert (case["datasets"], case["dataset_ids"]) == ([], [])
    for name in ("Enron", "Fixture", "enron", "fixture"):
        assert name not in response.text
    # A case reading two datasets and one reading one look alike: no count either.
    assert {k: v for k, v in listed["case-two"].items() if k not in ("id", "name")} == {
        k: v for k, v in listed["case-one"].items() if k not in ("id", "name")
    }


@pytest.mark.parametrize("role", sorted(WITH_ROLE))
def test_the_case_picker_is_unchanged_for_a_person_with_a_role(client: Any, role: str) -> None:
    _as(client, WITH_ROLE[role])
    listed = {c["id"]: c for c in client.get("/v1/investigations").json()}
    assert listed["case-two"]["datasets"] == ["Fixture Corp", "Enron corpus"]
    assert listed["case-two"]["dataset_ids"] == ["fixture", "enron"]
    assert listed["case-one"]["datasets"] == ["Enron corpus"]


# --- GET /v1/investigations/{id}/datasets: what a case reads -------------------------------------


def test_a_cases_datasets_are_not_named_to_a_person_with_no_role(client: Any) -> None:
    _as(client, NO_ROLE)
    two = client.get("/v1/investigations/case-two/datasets")
    one = client.get("/v1/investigations/case-one/datasets")
    assert (two.status_code, two.json()) == (200, [])
    # Two datasets and one answer alike, in body and length.
    assert (one.status_code, one.content) == (two.status_code, two.content)


@pytest.mark.parametrize("role", sorted(WITH_ROLE))
def test_a_cases_datasets_are_unchanged_for_a_person_with_a_role(client: Any, role: str) -> None:
    _as(client, WITH_ROLE[role])
    response = client.get("/v1/investigations/case-two/datasets")
    assert response.status_code == 200, response.text
    assert [d["name"] for d in response.json()] == ["Fixture Corp", "Enron corpus"]


# --- GET /v1/investigations/{id}/models/engines: the engine choice's reasons ---------------------


def test_a_case_engine_reason_names_no_dataset_to_a_person_with_no_role(client: Any) -> None:
    _as(client, NO_ROLE)
    two = client.get("/v1/investigations/case-two/models/engines")
    one = client.get("/v1/investigations/case-one/models/engines")
    assert two.status_code == 200, two.text
    for name in ("Enron", "Fixture", "enron", "fixture"):
        assert name not in two.text
    # Not "a dataset not known here" once per dataset: that would count them.
    assert (one.status_code, one.content) == (two.status_code, two.content)
    (gemini,) = [e for e in two.json()["engines"] if e["name"] == "gemini"]
    assert gemini["available"] is False  # still nothing leaves for a case it cannot name


@pytest.mark.parametrize("role", sorted(WITH_ROLE))
def test_a_case_engine_reason_is_unchanged_for_a_person_with_a_role(client: Any, role: str) -> None:
    _as(client, WITH_ROLE[role])
    response = client.get("/v1/investigations/case-two/models/engines")
    assert response.status_code == 200, response.text
    (gemini,) = [e for e in response.json()["engines"] if e["name"] == "gemini"]
    assert gemini["available"] is False
    assert "“Fixture Corp” and “Enron corpus” are set to egress none" in gemini["reason"]


# --- GET /v1/admin/datasets: every dataset, an administrator's -----------------------------------


@pytest.mark.parametrize("who", [NO_ROLE, NO_ROLE_EMPTY_UNIT, UNKNOWN_ROLES_ONLY])
def test_the_admin_list_is_refused_to_a_person_with_no_role(client: Any, who: Principal) -> None:
    _as(client, who)
    response = client.get("/v1/admin/datasets")
    assert response.status_code == 403
    assert response.json()["detail"] == {"error": "right_required", "right": "administer_system"}
    for name in ("Enron", "Fixture", "enron", "fixture", "Another"):
        assert name not in response.text


def test_the_admin_list_is_unchanged_for_an_administrator(client: Any) -> None:
    _as(client, ADMIN)
    response = client.get("/v1/admin/datasets")
    assert response.status_code == 200, response.text
    assert sorted(d["id"] for d in response.json()) == ["enron", "fixture", "theirs"]
