"""The screening-list connector's routes, and a dataset's lists, behind their rights and the dataset's
own gate (`06_DECISIONS.md` ADR-140 Amendment 13; rules 3 and 4: every read path has its
access-control case).

The real app and the real `get_principal` run; the token resolver, the cases and the stores stand
in. What a mistake would do, and the case that catches it:
- a person who may not load screening lists naming, importing, scheduling or reading the
  deployment's lists — `test_the_deployment_lists_are_for_whoever_may_load_screening_lists`;
- a subscription made, read or withdrawn for a dataset none of the person's cases loads into, or
  another unit's — told 404 as a missing dataset is —
  `test_a_dataset_s_subscriptions_are_reached_only_through_its_own_gate`;
- a subscription by a list's name instead of its id —
  `test_a_subscription_names_a_list_by_its_id_never_its_name`;
- a dataset offered a list it does not subscribe to, or another dataset's own list —
  `test_a_dataset_is_offered_only_its_own_and_its_subscribed_lists`;
- a dataset's own list imported from a file that is not the dataset's, or for a list its live
  model does not name, or replacing a version — `test_a_dataset_s_own_list_is_imported_from_its_own_files`;
- any of it unaudited — every case reads the audit.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.list_connector import InMemoryListRows, InMemoryListStore

from schemas.domain import Principal

TESTS = Path(__file__).parents[2]
GOLDEN = TESTS / "connectors" / "golden"
PEOPLE = {
    name: Principal(id=pid, clearance="SECRET", org_unit=unit, roles=[role])
    for name, pid, unit, role in (
        ("engineer", "eng-1", "unit-1", "data_engineer"),
        ("author", "aut-1", "unit-1", "source_author"),
        ("analyst", "ana-1", "unit-1", "analyst"),
        ("reader", "read-1", "unit-1", "data_engineer"),
        ("stranger", "str-1", "unit-2", "data_engineer"),
        ("admin", "adm-1", "unit-1", "osprey-admin"),
    )
}
CASES = {
    "eng-1": {"case-a": ["ds-a"], "case-c": ["ds-c"]},
    "aut-1": {"case-n": ["ds-a"]},
    "ana-1": {"case-y": ["ds-a"]},
    "read-1": {"case-r": ["ds-x", "ds-a"]},
    "str-1": {"case-s": ["ds-s"]},
    "adm-1": {},
}
MAPPING = (GOLDEN / "blank_client_list.mapping.json").read_text()


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Cases:
    async def list_for(self, principal: Principal) -> list[tuple[Any, str]]:
        return [(SimpleNamespace(id=c), "editor") for c in CASES[principal.id]]


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)

    def actions(self) -> list[str]:
        return [e["action"] for e in self.entries]


class _Models:
    """The live domain model's list ids per dataset: the routes read `live` alone."""

    def __init__(self, named: dict[str, list[str]]) -> None:
        self.named = named

    async def live(self, dataset_id: str) -> Any:
        ids = self.named.get(dataset_id)
        return None if ids is None else SimpleNamespace(reference_lists=ids)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[SimpleNamespace]:
    root = tmp_path / "ingest"
    for dataset in ("ds-a", "ds-c"):
        (root / "uploaded" / dataset).mkdir(parents=True)
    shutil.copy(GOLDEN / "blank_client_list.csv", root / "client.csv")
    (root / "uploaded" / "ds-a" / "estabs.csv").write_text(
        "estab_id,estab_name\nE1,HMP Synthetic One\nE2,HMP Synthetic Two\n"
    )
    (root / "uploaded" / "ds-c" / "numbers.csv").write_text("number,owner\n07700900001,X\n")
    # Another dataset's file shaped exactly as ds-a's list: reading it would succeed.
    (root / "uploaded" / "ds-c" / "estabs.csv").write_text("estab_id,estab_name\nE9,HMP Other\n")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    datasets = InMemoryDatasetStore()
    for d, unit in (("ds-a", "unit-1"), ("ds-c", "unit-1"), ("ds-x", "unit-1"), ("ds-s", "unit-2")):
        datasets.add(Dataset(id=d, name=d, owning_unit=unit, created_by="s",
                             created_at=datetime(2026, 1, 1, tzinfo=UTC)))  # fmt: skip
    for person in CASES.values():
        for case, reads in person.items():
            datasets.cases[case] = reads
    audit, lists, rows = _Audit(), InMemoryListStore(), InMemoryListRows()
    models = _Models({"ds-a": ["rl-est"], "ds-c": ["rl-num"]})
    state = {
        "principal_resolver": _Resolver(), "investigations": _Cases(), "datasets": datasets,
        "audit": audit, "list_store": lists, "list_rows": rows, "target_models": models,
    }  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    # The blank golden list is one of the connector's synthetic files (rule 9), by its SHA-256.
    yield SimpleNamespace(client=TestClient(app), root=root, audit=audit, lists=lists, rows=rows,
                          models=models)  # fmt: skip


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


def _add_list(world: SimpleNamespace, name: str = "Client list", person: str = "engineer") -> Any:
    body = {"name": name, "template": "blank", "location": "client.csv",
            "mapping": __import__("json").loads(MAPPING)}  # fmt: skip
    return world.client.post("/v1/studio/screening-lists", json=body, headers=_as(person))


def _imported(world: SimpleNamespace, name: str = "Client list") -> str:
    made = _add_list(world, name)
    assert made.status_code == 201, made.text
    list_id = made.json()["id"]
    done = world.client.post(f"/v1/studio/screening-lists/{list_id}/refresh",
                             headers=_as("engineer"))  # fmt: skip
    assert done.status_code == 200 and done.json()["outcome"] == "updated", done.text
    return str(list_id)


def test_the_deployment_lists_are_for_whoever_may_load_screening_lists(
    world: SimpleNamespace,
) -> None:
    list_id = _imported(world)
    again = world.client.post(f"/v1/studio/screening-lists/{list_id}/refresh",
                              headers=_as("engineer"))  # fmt: skip
    assert again.json()["outcome"] == "unchanged"
    schedule = {"schedule": {"every": "weekly", "hour": 6, "weekday": 1}}
    for person in ("author", "analyst"):
        calls = [
            world.client.get("/v1/studio/screening-lists", headers=_as(person)),
            _add_list(world, "Another", person),
            world.client.post(f"/v1/studio/screening-lists/{list_id}/refresh", headers=_as(person)),
            world.client.get(f"/v1/studio/screening-lists/{list_id}/imports", headers=_as(person)),
            world.client.put(f"/v1/studio/screening-lists/{list_id}/schedule", json=schedule,
                             headers=_as(person)),
        ]  # fmt: skip
        assert [c.status_code for c in calls] == [403] * 5, person
    assert len(world.lists._lists) == 1
    for person in ("engineer", "admin"):
        listed = world.client.get("/v1/studio/screening-lists", headers=_as(person))
        assert [r["version"] for r in listed.json()] == [1], person
    set_ = world.client.put(f"/v1/studio/screening-lists/{list_id}/schedule", json=schedule,
                            headers=_as("admin"))  # fmt: skip
    assert set_.status_code == 200 and "06:00" in set_.json()["schedule_words"], set_.text
    bad = world.client.put(f"/v1/studio/screening-lists/{list_id}/schedule",
                           json={"schedule": {"every": "weekly", "hour": 6}},
                           headers=_as("admin"))  # fmt: skip
    assert bad.status_code == 422
    imports = world.client.get(f"/v1/studio/screening-lists/{list_id}/imports",
                               headers=_as("engineer")).json()  # fmt: skip
    assert [i["outcome"] for i in imports] == ["unchanged", "updated"]
    assert {"add_deployment_list", "deployment_list_refreshed", "list_deployment_lists",
            "deployment_list_schedule_set", "list_deployment_list_imports"} <= set(
        world.audit.actions())  # fmt: skip


def test_a_location_outside_the_ingest_folder_is_refused_on_naming(world: SimpleNamespace) -> None:
    body = {"name": "Escape", "template": "ofsi_consolidated", "location": "../../etc/passwd"}
    refused = world.client.post("/v1/studio/screening-lists", json=body, headers=_as("engineer"))
    assert refused.status_code == 422 and "outside the ingest folder" in refused.text
    missing = world.client.post("/v1/studio/screening-lists/nope/refresh", headers=_as("engineer"))
    assert missing.status_code == 404


def test_a_dataset_s_subscriptions_are_reached_only_through_its_own_gate(
    world: SimpleNamespace,
) -> None:
    list_id = _imported(world)
    url = f"/v1/datasets/ds-a/screening-subscriptions/{list_id}"
    assert world.client.put(url, headers=_as("engineer")).status_code == 200
    for person, expected in (("stranger", 404), ("reader", 404), ("analyst", 403)):
        reads = world.client.get("/v1/datasets/ds-a/screening-subscriptions", headers=_as(person))
        puts = world.client.put(url, headers=_as(person))
        deletes = world.client.delete(url, headers=_as(person))
        assert (reads.status_code, puts.status_code, deletes.status_code) == (expected,) * 3, person
    missing = world.client.get("/v1/datasets/no-such/screening-subscriptions",
                               headers=_as("stranger"))  # fmt: skip
    other = world.client.get("/v1/datasets/ds-a/screening-subscriptions", headers=_as("stranger"))
    assert missing.json() == other.json()
    held = world.client.get("/v1/datasets/ds-a/screening-subscriptions", headers=_as("author"))
    assert held.status_code == 200 and held.json()["subscribed"] == [list_id]
    gone = world.client.delete(url, headers=_as("author"))
    assert gone.status_code == 200 and gone.json()["subscribed"] == []
    assert {"dataset_list_subscribed", "dataset_list_subscriptions",
            "dataset_list_unsubscribed"} <= set(world.audit.actions())  # fmt: skip


def test_a_subscription_names_a_list_by_its_id_never_its_name(world: SimpleNamespace) -> None:
    _imported(world)
    by_name = world.client.put("/v1/datasets/ds-a/screening-subscriptions/Client list",
                               headers=_as("engineer"))  # fmt: skip
    assert by_name.status_code == 404
    assert world.lists._subscriptions == {} or world.lists._subscriptions == {"ds-a": set()}


def test_a_dataset_is_offered_only_its_own_and_its_subscribed_lists(world: SimpleNamespace) -> None:
    subscribed = _imported(world, "Client list")
    _imported(world, "Second list")
    world.client.put(f"/v1/datasets/ds-a/screening-subscriptions/{subscribed}",
                     headers=_as("engineer"))  # fmt: skip
    for dataset, file, list_id, name, key in (
        ("ds-a", "estabs.csv", "rl-est", "establishments", "estab_id"),
        ("ds-c", "numbers.csv", "rl-num", "number_owners", "number"),
    ):
        body = {"location": str(world.root / "uploaded" / dataset / file), "name": name,
                "key_column": key}  # fmt: skip
        done = world.client.post(f"/v1/datasets/{dataset}/reference-lists/{list_id}/import",
                                 json=body, headers=_as("engineer"))  # fmt: skip
        assert done.status_code == 200, done.text
    offered_a = world.client.get("/v1/datasets/ds-a/reference-lists/offered",
                                 headers=_as("author"))  # fmt: skip
    assert [(o["name"], o["deployment_wide"]) for o in offered_a.json()] == [
        ("establishments", False), ("Client list", True)]  # fmt: skip
    offered_c = world.client.get("/v1/datasets/ds-c/reference-lists/offered",
                                 headers=_as("engineer"))  # fmt: skip
    assert [o["name"] for o in offered_c.json()] == ["number_owners"]
    for person, expected in (("stranger", 404), ("reader", 404), ("analyst", 403)):
        got = world.client.get("/v1/datasets/ds-a/reference-lists/offered", headers=_as(person))
        assert got.status_code == expected, person
    assert "offered_reference_lists" in world.audit.actions()
    world.models.named["ds-a"] = []  # the live model no longer names it: kept, but not offered
    offered_a = world.client.get("/v1/datasets/ds-a/reference-lists/offered",
                                 headers=_as("author"))  # fmt: skip
    assert [o["name"] for o in offered_a.json()] == ["Client list"]


def test_a_dataset_s_own_list_is_imported_from_its_own_files(world: SimpleNamespace) -> None:
    url = "/v1/datasets/ds-a/reference-lists/rl-est/import"
    own = str(world.root / "uploaded" / "ds-a" / "estabs.csv")
    first = {"location": own, "name": "establishments", "key_column": "estab_id"}
    theirs = str(world.root / "uploaded" / "ds-c" / "estabs.csv")
    not_ours = world.client.post(url, json={**first, "location": theirs}, headers=_as("engineer"))
    nowhere = world.client.post(url, json={**first, "location": "/etc/passwd"},
                                headers=_as("engineer"))  # fmt: skip
    assert not_ours.status_code == nowhere.status_code == 422
    assert not_ours.json() == nowhere.json()
    assert "not one of this dataset's files" in not_ours.text
    assert world.rows.files == {}
    unnamed = world.client.post("/v1/datasets/ds-a/reference-lists/rl-other/import", json=first,
                                headers=_as("engineer"))  # fmt: skip
    assert unnamed.status_code == 422 and "names no list" in unnamed.text
    done = world.client.post(url, json=first, headers=_as("author"))
    assert done.status_code == 200 and done.json()["version"] == 1, done.text
    again = world.client.post(url, json={"location": own}, headers=_as("author"))
    assert again.json()["outcome"] == "unchanged" and again.json()["version"] == 1
    for person, expected in (("stranger", 404), ("reader", 404), ("analyst", 403)):
        got = world.client.post(url, json=first, headers=_as(person))
        assert got.status_code == expected, person
    assert world.audit.actions().count("import_dataset_own_list") == 2
