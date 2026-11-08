"""Admin › Datasets, L2.4 part 2 (ADR-145 decision 8 and Amendment 4 decisions 3, 6 and 7; ADR-143
Amendment 2 decisions 1 and 2; ADR-112 Amendments 4 and 5). The real app, `require_right` and the
routes run; the stores are stand-ins that hold what the real ones hold.

What a mistake would do, and the case that catches it:

- a route answered without `administer_system`, or refused to a holder of it alone:
  `test_every_datasets_route_refuses_without_the_right` and
  `test_a_holder_of_the_right_alone_is_answered`;
- a layer's contents (an item's label or property) on any route, or a field beyond the counts:
  `test_no_route_returns_a_layers_contents`, red with one label planted into a response
  (`test_the_contents_check_fails_with_a_label_planted`);
- the counts filtered in the Conduit rather than taken by the store, or read for the caller's own
  cases only: `test_an_administrator_sees_every_cases_counts_taken_by_the_store`;
- a removed case's row telling more than an open one's:
  `test_a_removed_row_has_an_open_rows_fields`;
- *Change owner…* given a service account, or against Admin › System's setting, or unaudited:
  `test_change_owner_refuses_in_words`, `test_change_owner_replaces_the_authors_and_is_audited`;
- the approvers counted wrongly: `test_the_approvers_are_the_authors_holding_review_promotions`,
  with `test_no_one_approves_when_no_role_holds_review_promotions`;
- a removed case's *Merge* or *Delete* offered for an open case, a case through a composite, or a
  merge by someone not an Author, or writing anything: the `test_a_dry_run_…` cases.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api.app import app
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import AccessLevel, Investigation

from ontology.handling import load_uk_le_scheme
from ports.graph import DatasetFootprint
from schemas.admin import PersonAccount
from schemas.dataset_model import HomeCase
from schemas.domain import Principal
from schemas.rights import ROLE_RIGHTS, Right

T0 = datetime(2026, 1, 1, tzinfo=UTC)
PEOPLE = {
    name: Principal(id=pid, clearance="SECRET", org_unit="unit-1", roles=roles)
    for name, pid, roles in (
        ("admin", "adm-1", ["osprey-admin"]),
        ("author_admin", "adm-2", ["osprey-admin"]),
        ("right_alone", "adm-3", ["right:administer_system"]),
        ("engineer", "eng-1", ["data_engineer"]),
        ("analyst", "ana-1", ["analyst"]),
    )
}
ROLES = {p.id: p.roles for p in PEOPLE.values()}
PERSONS = {"adm-1", "adm-2", "adm-3", "eng-1", "ana-1", "per-2"}
ROBOT = "service-account-loader"

#: What the layers hold, which no response may carry: each item's label and a property value.
CONTENTS = ("Drawn suspect Kestrel", "07700 900123", "Blue Transit van")


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Names:
    async def people(self, ids: Any) -> set[str] | None:
        return {i for i in ids if i in PERSONS}

    async def display_names(self, ids: Any) -> dict[str, str]:
        return {i: f"Name of {i}" for i in ids if i in PERSONS}


class _Directory:
    """The identity provider's people, with their roles (`IdentityAdmin.list_people`)."""

    async def list_people(self) -> list[PersonAccount]:
        return [
            PersonAccount(id=i, username=i, name=i, enabled=True, roles=list(ROLES.get(i, [])))
            for i in sorted(PERSONS)
        ]


class _Cases:
    """Cases, open and removed, and their grants, as the real store holds them."""

    def __init__(self) -> None:
        self.made: dict[str, Investigation] = {}
        self.grants: dict[str, dict[str, AccessLevel]] = {}
        self.removed: set[str] = set()

    def seed(self, case_id: str, name: str, grants: dict[str, AccessLevel]) -> None:
        self.made[case_id] = Investigation(
            id=case_id, name=name, created_at=T0, created_by="seed", owning_unit="unit-1"
        )
        self.grants[case_id] = dict(grants)

    async def admin_states(self, ids: Sequence[str]) -> dict[str, tuple[str, bool]]:
        return {i: (self.made[i].name, i in self.removed) for i in ids if i in self.made}

    async def list_grants(self, case_id: str) -> dict[str, AccessLevel]:
        return dict(self.grants.get(case_id, {}))

    async def set_grant(self, case_id: str, account: str, level: AccessLevel, *, by: Any) -> None:
        self.grants[case_id][account] = level

    async def remove_grant(self, case_id: str, account: str, *, by: Any) -> None:
        self.grants[case_id].pop(account, None)


class _Graph:
    """The graph store's footprint read: numbers per dataset, and a note of what it was asked.
    The items' labels are held here, as the store holds them, to prove they never come out."""

    def __init__(self) -> None:
        self.held: dict[str, DatasetFootprint] = {}
        self.items: dict[str, list[str]] = {}
        self.asked: list[list[str]] = []

    async def dataset_footprints(self, dataset_ids: Sequence[str]) -> dict[str, DatasetFootprint]:
        self.asked.append(list(dataset_ids))
        return {d: self.held.get(d, DatasetFootprint()) for d in dataset_ids}


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


async def _layer(datasets: InMemoryDatasetStore, case_id: str, name: str) -> str:
    return await datasets.ensure_layer(case_id, unit="unit-1", created_by="seed", case_name=name)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    import asyncio

    datasets = InMemoryDatasetStore()
    for ds_id, name in (("ds-a", "Prison records"), ("ds-b", "Custody suites")):
        datasets.add(
            Dataset(id=ds_id, name=name, owning_unit="unit-1", created_at=T0, created_by="eng-1")
        )
    datasets.add(
        Dataset(id="cmp-1", name="Both", owning_unit="unit-1", created_at=T0,
                created_by="eng-1", kind="composite", members=["ds-a", "ds-b"])
    )  # fmt: skip
    cases, graph = _Cases(), _Graph()
    # The home case (its Authors adm-2 and eng-1), an open working case and a removed one, all of
    # whose members exclude the administrator adm-1; and a case reading ds-a through a composite.
    cases.seed(
        "home-a", "Prison records", {"adm-2": AccessLevel.AUTHOR, "eng-1": AccessLevel.AUTHOR}
    )
    cases.seed("open-1", "Op Kestrel", {"ana-1": AccessLevel.AUTHOR})
    cases.seed("gone-1", "Op Heron", {"ana-1": AccessLevel.AUTHOR})
    cases.seed("via-1", "Op Merlin", {"ana-1": AccessLevel.AUTHOR})
    cases.removed.add("gone-1")
    for case_id in ("home-a", "open-1", "gone-1"):
        datasets.cases[case_id] = ["ds-a"]
    datasets.cases["via-1"] = ["cmp-1"]
    datasets.homes["ds-a"] = HomeCase(
        dataset_id="ds-a", investigation_id="home-a", made_at=T0, made_by="eng-1"
    )
    layers = {
        c: asyncio.run(_layer(datasets, c, cases.made[c].name))
        for c in ("home-a", "open-1", "gone-1", "via-1")
    }
    graph.held[layers["open-1"]] = DatasetFootprint(nodes=3, edges=2, properties_bytes=700)
    graph.held[layers["gone-1"]] = DatasetFootprint(
        nodes=5, edges=4, properties_bytes=2000, picture_bytes=48_000
    )
    graph.items = {layers["open-1"]: list(CONTENTS[:2]), layers["gone-1"]: [CONTENTS[2]]}
    audit = _Audit()
    state = {
        "principal_resolver": _Resolver(), "investigations": cases, "datasets": datasets,
        "graph": graph, "audit": audit, "principal_names": _Names(),
        "identity_admin": _Directory(), "handling_scheme": load_uk_le_scheme(),
    }  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(
        client=TestClient(app), datasets=datasets, cases=cases, graph=graph, audit=audit,
        layers=layers,
    )  # fmt: skip


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


#: Every Admin › Datasets route of this step, with a body that would be accepted.
ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/v1/admin/datasets", None),
    ("GET", "/v1/admin/datasets/ds-a/cases", None),
    ("GET", "/v1/admin/datasets/ds-a/authors", None),
    ("PUT", "/v1/admin/datasets/ds-a/owners", {"people": ["per-2"]}),
    ("PUT", "/v1/admin/datasets/ds-a/promotion-policy",
     {"promotion_policy": "second_person_reviews"}),
    ("POST", "/v1/admin/datasets/ds-a/cases/gone-1/delete/dry-run", None),
    ("POST", "/v1/admin/datasets/ds-a/cases/gone-1/merge/dry-run", None),
    ("GET", "/v1/admin/settings/dataset-owners", None),
    ("PUT", "/v1/admin/settings/dataset-owners", {"owners_may_be": "people_only"}),
]  # fmt: skip


def _call(world: SimpleNamespace, person: str, method: str, path: str, body: Any) -> Any:
    return world.client.request(method, path, json=body, headers=_as(person))


@pytest.mark.parametrize(("method", "path", "body"), ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
@pytest.mark.parametrize("person", ["engineer", "analyst"])
def test_every_datasets_route_refuses_without_the_right(
    world: SimpleNamespace, person: str, method: str, path: str, body: Any
) -> None:
    answer = _call(world, person, method, path, body)
    assert answer.status_code == 403, answer.text
    assert not [e for e in world.audit.entries if e["principal"].id == PEOPLE[person].id]


@pytest.mark.parametrize(("method", "path", "body"), ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_a_holder_of_the_right_alone_is_answered(
    world: SimpleNamespace, method: str, path: str, body: Any
) -> None:
    """The reverse direction (part 1's review): `right:administer_system` alone is enough. The
    merge dry run then refuses in words for not being an Author, which is its own check."""
    answer = _call(world, "right_alone", method, path, body)
    if path.endswith("/merge/dry-run"):
        assert answer.status_code == 403 and answer.json()["error"] == "not_an_author"
    else:
        assert answer.status_code == 200, answer.text


def _every_answer(world: SimpleNamespace) -> list[str]:
    texts = []
    for method, path, body in ROUTES:
        if method == "PUT":
            continue
        for person in ("admin", "author_admin"):
            texts.append(_call(world, person, method, path, body).text)
    return texts


def _contents_in(texts: list[str]) -> list[str]:
    return [c for c in CONTENTS for t in texts if c in t]


#: Every field a linked case's row may carry: the counts, its name and state, and nothing else.
ROW_FIELDS = {
    "investigation_id", "name", "state", "home_case", "through", "items", "links", "size_bytes",
}  # fmt: skip


def test_no_route_returns_a_layers_contents(world: SimpleNamespace) -> None:
    assert _contents_in(_every_answer(world)) == []
    rows = _call(world, "admin", "GET", "/v1/admin/datasets/ds-a/cases", None).json()["cases"]
    assert rows and all(set(r) == ROW_FIELDS for r in rows)


def test_the_contents_check_fails_with_a_label_planted(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: one item's label added to the response, in the shape the route builds."""
    real = app_module._linked_cases

    async def planted(dataset: Any, *args: Any) -> Any:
        rows = await real(dataset, *args)
        return [r.model_copy(update={"name": f"{r.name}: {CONTENTS[0]}"}) for r in rows]

    monkeypatch.setattr(app_module, "_linked_cases", planted)
    assert CONTENTS[0] in _contents_in(_every_answer(world))


def test_an_administrator_sees_every_cases_counts_taken_by_the_store(
    world: SimpleNamespace,
) -> None:
    answer = _call(world, "admin", "GET", "/v1/admin/datasets/ds-a/cases", None)
    rows = {r["investigation_id"]: r for r in answer.json()["cases"]}
    assert set(rows) == {"home-a", "open-1", "gone-1", "via-1"}
    assert (rows["open-1"]["items"], rows["open-1"]["links"], rows["open-1"]["size_bytes"]) == (
        3, 2, 700,
    )  # fmt: skip
    assert rows["gone-1"]["size_bytes"] == 2000 + 48_000
    assert rows["home-a"]["home_case"] and not rows["open-1"]["home_case"]
    assert rows["via-1"]["through"] == "Both" and rows["open-1"]["through"] is None
    # Taken by the store, for every case's layer, the administrator a member of none of them.
    (asked,) = world.graph.asked
    assert set(asked) == set(world.layers.values())
    assert all("adm-1" not in world.cases.grants[c] for c in rows)
    (entry,) = [e for e in world.audit.entries if e["action"] == "list_dataset_cases"]
    assert entry["result_cardinality"] == 4


def test_a_removed_row_has_an_open_rows_fields(world: SimpleNamespace) -> None:
    rows = _call(world, "admin", "GET", "/v1/admin/datasets/ds-a/cases", None).json()["cases"]
    by_state = {r["state"]: r for r in rows if r["investigation_id"] in ("open-1", "gone-1")}
    assert set(by_state["open"]) == set(by_state["removed"]) == ROW_FIELDS


def test_the_datasets_list_carries_kind_and_policy(world: SimpleNamespace) -> None:
    listed = {d["id"]: d for d in _call(world, "admin", "GET", "/v1/admin/datasets", None).json()}
    assert listed["cmp-1"]["kind"] == "composite" and listed["ds-a"]["kind"] == "source"
    assert listed["ds-a"]["promotion_policy"] == "author_promotes"
    assert not [d for d in listed.values() if d["name"].startswith("Analyst layer")]


def test_the_promotion_policy_is_set_and_audited(world: SimpleNamespace) -> None:
    answer = _call(world, "admin", "PUT", "/v1/admin/datasets/ds-a/promotion-policy",
                   {"promotion_policy": "second_person_reviews"})  # fmt: skip
    assert answer.json()["promotion_policy"] == "second_person_reviews"
    (entry,) = [e for e in world.audit.entries if e["action"] == "set_dataset_promotion_policy"]
    assert entry["resolved_query"] == {
        "dataset_id": "ds-a", "before": "author_promotes", "after": "second_person_reviews",
    }  # fmt: skip
    layer = world.layers["open-1"]
    refused = _call(world, "admin", "PUT", f"/v1/admin/datasets/{layer}/promotion-policy",
                    {"promotion_policy": "author_promotes"})  # fmt: skip
    assert refused.status_code == 404, "a layer is never a dataset Admin can set"


def test_the_approvers_are_the_authors_holding_review_promotions(world: SimpleNamespace) -> None:
    body = _call(world, "admin", "GET", "/v1/admin/datasets/ds-a/authors", None).json()
    assert body["has_home_case"] and body["team"] is None
    assert {p["id"]: p["approves"] for p in body["people"]} == {"adm-2": False, "eng-1": True}
    assert body["people"][1]["name"] == "Name of eng-1"


def test_no_one_approves_when_no_role_holds_review_promotions(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: with the right taken from the Data Engineer, the same Author approves nothing,
    so the count is the right's and not the role's name."""
    monkeypatch.setitem(
        ROLE_RIGHTS, "data_engineer", ROLE_RIGHTS["data_engineer"] - {Right.REVIEW_PROMOTIONS}
    )
    body = _call(world, "admin", "GET", "/v1/admin/datasets/ds-a/authors", None).json()
    assert [p["id"] for p in body["people"] if p["approves"]] == []


def test_a_dataset_not_yet_live_has_no_authors(world: SimpleNamespace) -> None:
    body = _call(world, "admin", "GET", "/v1/admin/datasets/ds-b/authors", None).json()
    assert body == {"dataset_id": "ds-b", "has_home_case": False, "people": [], "team": None}


@pytest.mark.parametrize(
    ("setting", "owners", "words"),
    [
        ("people_and_teams", {"people": [ROBOT]}, "never a service account"),
        ("people_and_teams", {"people": ["per-2", "no-such-account"]}, "never a service account"),
        ("people_and_teams", {"team": "Prison intel data team"}, "until teams are built"),
        ("people_only", {"team": "Prison intel data team"}, "allows people only"),
        ("teams_only", {"people": ["per-2"]}, "allows teams only"),
    ],
)
def test_change_owner_refuses_in_words(
    world: SimpleNamespace, setting: str, owners: Any, words: str
) -> None:
    world.datasets.owners_may_be = setting
    before = dict(world.cases.grants["home-a"])
    answer = _call(world, "admin", "PUT", "/v1/admin/datasets/ds-a/owners", owners)
    assert answer.status_code == 409 and words in answer.json()["detail"], answer.text
    assert world.cases.grants["home-a"] == before
    assert not [e for e in world.audit.entries if e["action"] == "change_dataset_owners"]


def test_change_owner_names_someone_and_waits_for_make_live(world: SimpleNamespace) -> None:
    empty = _call(world, "admin", "PUT", "/v1/admin/datasets/ds-a/owners", {"people": []})
    assert empty.status_code == 422
    not_live = _call(world, "admin", "PUT", "/v1/admin/datasets/ds-b/owners", {"people": ["per-2"]})
    assert not_live.status_code == 409 and "first Make live" in not_live.json()["detail"]


def test_change_owner_replaces_the_authors_and_is_audited(world: SimpleNamespace) -> None:
    answer = _call(world, "admin", "PUT", "/v1/admin/datasets/ds-a/owners",
                   {"people": ["per-2", "eng-1"]})  # fmt: skip
    assert answer.status_code == 200, answer.text
    assert world.cases.grants["home-a"] == {
        "eng-1": AccessLevel.AUTHOR, "per-2": AccessLevel.AUTHOR,
    }  # fmt: skip
    assert [p["id"] for p in answer.json()["people"]] == ["eng-1", "per-2"]
    (entry,) = [e for e in world.audit.entries if e["action"] == "change_dataset_owners"]
    assert entry["resolved_query"] == {
        "dataset_id": "ds-a", "before": ["adm-2", "eng-1"], "after": ["eng-1", "per-2"],
    }  # fmt: skip
    assert entry["investigation_id"] == "home-a"


def _dry(world: SimpleNamespace, person: str, case: str, action: str, ds: str = "ds-a") -> Any:
    return _call(world, person, "POST", f"/v1/admin/datasets/{ds}/cases/{case}/{action}/dry-run",
                 None)  # fmt: skip


def _nothing_written(world: SimpleNamespace, before: str) -> None:
    after = json.dumps(
        {"grants": world.cases.grants, "removed": sorted(world.cases.removed),
         "cases": world.datasets.cases}, default=str, sort_keys=True,
    )  # fmt: skip
    assert after == before


def _state(world: SimpleNamespace) -> str:
    return json.dumps(
        {"grants": world.cases.grants, "removed": sorted(world.cases.removed),
         "cases": world.datasets.cases}, default=str, sort_keys=True,
    )  # fmt: skip


def test_a_dry_run_counts_and_writes_nothing(world: SimpleNamespace) -> None:
    before = _state(world)
    merged = _dry(world, "author_admin", "gone-1", "merge")
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert (body["items"], body["links"], body["size_bytes"]) == (5, 4, 50_000)
    assert "into Prison records" in body["would"] and "Nothing has been written" in body["would"]
    deleted = _dry(world, "admin", "gone-1", "delete")
    assert deleted.status_code == 200 and "never touched" in deleted.json()["would"]
    _nothing_written(world, before)
    actions = [e["action"] for e in world.audit.entries]
    assert actions.count("dry_run_layer_merge") == actions.count("dry_run_layer_delete") == 1


@pytest.mark.parametrize("action", ["merge", "delete"])
def test_a_dry_run_refuses_an_open_case(world: SimpleNamespace, action: str) -> None:
    answer = _dry(world, "author_admin", "open-1", action)
    assert answer.status_code == 409 and answer.json()["error"] == "case_open"


@pytest.mark.parametrize("case", ["via-1", "no-such-case"])
def test_a_dry_run_refuses_a_case_not_linked_directly(world: SimpleNamespace, case: str) -> None:
    world.cases.removed.add("via-1")
    answer = _dry(world, "author_admin", case, "delete")
    assert answer.status_code == 404 and answer.json()["error"] == "case_not_linked"


def test_a_dry_run_merge_is_an_authors_and_says_who_they_are(world: SimpleNamespace) -> None:
    answer = _dry(world, "admin", "gone-1", "merge")
    assert answer.status_code == 403 and answer.json()["error"] == "not_an_author"
    assert "adm-2, eng-1" in answer.json()["detail"]
    assert not [e for e in world.audit.entries if e["action"].startswith("dry_run")]


def test_a_dry_run_merge_into_a_composite_is_refused(world: SimpleNamespace) -> None:
    world.cases.removed.add("via-1")
    answer = _dry(world, "author_admin", "via-1", "merge", ds="cmp-1")
    assert answer.status_code == 409 and answer.json()["error"] == "composite_read_only"
