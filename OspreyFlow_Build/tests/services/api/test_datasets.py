"""A case's datasets (`06_DECISIONS.md` ADR-099): named when the case is made, taken by a branch,
changed by its Author, never one of another unit's.

What a mistake here would do, and the case that catches it:

- a case made with no dataset named would read nothing, or everything
  (`test_a_case_made_naming_no_dataset_gets_one_of_its_own`);
- a case allowed another unit's dataset would read that unit's data
  (`test_a_case_cannot_be_made_over_another_units_dataset_and_none_is_left_behind`,
  `test_the_author_cannot_widen_a_case_to_another_units_dataset`);
- a refusal that told "another unit's" from "no such dataset" would say what another unit holds
  (`test_another_units_dataset_and_a_missing_one_are_refused_alike`);
- a branch reading more, or less, than its parent (`test_a_branch_reads_what_its_parent_reads`).

Route levels are in `test_investigation_levels.py`'s table; this file is behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_audit, get_datasets, get_investigations, get_principal
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import AccessLevel, Investigation, InvestigationNotFoundError

from schemas.domain import Principal

ALICE = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
CAROL = Principal(id="carol", clearance="OFFICIAL", org_unit="unit-2", roles=["analyst"])


def _dataset(dataset_id: str, unit: str, name: str) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=name,
        owning_unit=unit,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        created_by="seed",
    )


class _Investigations:
    def __init__(self) -> None:
        self.made: list[Investigation] = []

    async def create(
        self,
        principal: Principal,
        *,
        name: str,
        branched_from: str | None = None,
        domains: list[str] | None = None,
    ) -> Investigation:
        case = Investigation(
            id=f"case-{len(self.made) + 1}",
            name=name,
            created_at=datetime.now(UTC),
            created_by=principal.id,
            owning_unit=principal.org_unit,
            branched_from=branched_from,
        )
        self.made.append(case)
        return case

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        for case in self.made:
            if case.id == investigation_id and case.owning_unit == principal.org_unit:
                return case
        raise InvestigationNotFoundError(investigation_id)

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return [(c, AccessLevel.AUTHOR) for c in self.made if c.owning_unit == principal.org_unit]

    async def hidden_tab_ids(self, principal: Principal) -> set[str]:
        return set()


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


@pytest.fixture
def store() -> InMemoryDatasetStore:
    held = InMemoryDatasetStore()
    held.add(_dataset("enron", "unit-1", "Enron corpus"))
    held.add(_dataset("fixture", "unit-1", "Fixture Corp"))
    held.add(_dataset("theirs", "unit-2", "Another unit's"))
    return held


@pytest.fixture
def setup(store: InMemoryDatasetStore):  # type: ignore[no-untyped-def]
    investigations = _Investigations()
    audit = _Audit()
    who = {"principal": ALICE}
    app.dependency_overrides[get_investigations] = lambda: investigations
    app.dependency_overrides[get_principal] = lambda: who["principal"]
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_datasets] = lambda: store
    yield TestClient(app, raise_server_exceptions=False), investigations, audit, who
    app.dependency_overrides.clear()


def test_a_case_made_naming_no_dataset_gets_one_of_its_own(setup, store) -> None:  # type: ignore[no-untyped-def]
    client, _, _, _ = setup
    made = client.post("/v1/investigations", json={"name": "Shipping leads"}).json()
    (own,) = client.get(f"/v1/investigations/{made['id']}/datasets").json()
    assert own["name"] == "Shipping leads" and own["owning_unit"] == "unit-1"


def test_a_case_made_over_named_datasets_reads_those_in_order(setup) -> None:  # type: ignore[no-untyped-def]
    client, _, audit, _ = setup
    made = client.post(
        "/v1/investigations", json={"name": "Both", "dataset_ids": ["fixture", "enron"]}
    ).json()
    read = client.get(f"/v1/investigations/{made['id']}/datasets").json()
    assert [d["id"] for d in read] == ["fixture", "enron"]
    assert audit.records[-1]["resolved_query"] == {"dataset_ids": ["fixture", "enron"]}


def test_a_case_cannot_be_made_over_another_units_dataset_and_none_is_left_behind(setup) -> None:  # type: ignore[no-untyped-def]
    client, investigations, _, _ = setup
    refused = client.post("/v1/investigations", json={"name": "X", "dataset_ids": ["theirs"]})
    assert refused.status_code == 422 and refused.json() == {"error": "dataset_refused"}
    assert investigations.made == []


def test_another_units_dataset_and_a_missing_one_are_refused_alike(setup) -> None:  # type: ignore[no-untyped-def]
    client, _, _, _ = setup
    theirs = client.post("/v1/investigations", json={"name": "X", "dataset_ids": ["theirs"]})
    missing = client.post("/v1/investigations", json={"name": "X", "dataset_ids": ["nope"]})
    assert (theirs.status_code, theirs.json()) == (missing.status_code, missing.json())


def test_the_author_changes_what_a_case_reads_and_it_is_audited(setup) -> None:  # type: ignore[no-untyped-def]
    client, _, audit, _ = setup
    made = client.post("/v1/investigations", json={"name": "C", "dataset_ids": ["fixture"]}).json()
    changed = client.put(
        f"/v1/investigations/{made['id']}/datasets", json={"dataset_ids": ["fixture", "enron"]}
    )
    assert [d["id"] for d in changed.json()] == ["fixture", "enron"]
    record = audit.records[-1]
    assert record["action"] == "set_case_datasets"
    assert record["resolved_query"] == {"before": ["fixture"], "after": ["fixture", "enron"]}


def test_the_author_cannot_widen_a_case_to_another_units_dataset(setup) -> None:  # type: ignore[no-untyped-def]
    client, _, _, _ = setup
    made = client.post("/v1/investigations", json={"name": "C", "dataset_ids": ["fixture"]}).json()
    refused = client.put(
        f"/v1/investigations/{made['id']}/datasets", json={"dataset_ids": ["fixture", "theirs"]}
    )
    assert refused.status_code == 422
    still = client.get(f"/v1/investigations/{made['id']}/datasets").json()
    assert [d["id"] for d in still] == ["fixture"]


def test_a_case_cannot_be_left_reading_nothing(setup) -> None:  # type: ignore[no-untyped-def]
    client, _, _, _ = setup
    made = client.post("/v1/investigations", json={"name": "C", "dataset_ids": ["fixture"]}).json()
    refused = client.put(f"/v1/investigations/{made['id']}/datasets", json={"dataset_ids": []})
    assert refused.status_code == 422


def test_the_datasets_listed_are_the_callers_units_only(setup) -> None:  # type: ignore[no-untyped-def]
    client, _, _, who = setup
    assert [d["id"] for d in client.get("/v1/datasets").json()] == ["enron", "fixture"]
    who["principal"] = CAROL
    assert [d["id"] for d in client.get("/v1/datasets").json()] == ["theirs"]


async def test_a_branch_reads_what_its_parent_reads(store: InMemoryDatasetStore) -> None:
    await store.set_for_case("parent", ["fixture", "enron"], ALICE)
    await store.copy_case("parent", "branch")
    assert await store.ids_of_case("branch") == ["fixture", "enron"]


def test_the_case_list_names_what_each_case_reads(setup) -> None:  # type: ignore[no-untyped-def]
    client, _, _, _ = setup
    client.post("/v1/investigations", json={"name": "Both", "dataset_ids": ["fixture", "enron"]})
    (listed,) = client.get("/v1/investigations").json()
    assert listed["datasets"] == ["Fixture Corp", "Enron corpus"]
    # Their ids, in the same order, so the picker tells alike names apart (ADR-099 Amendment 6).
    assert listed["dataset_ids"] == ["fixture", "enron"]

