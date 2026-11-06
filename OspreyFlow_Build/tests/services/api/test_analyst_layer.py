"""A case's analyst layer and its read set (`06_DECISIONS.md` ADR-143 decision 1; ADR-099
Amendments 12 and 13; ADR-140 R8).

What a mistake here would do, and the case that catches it:

- a request under a case reading less than its source and its layer, or more (another case's
  layer): `test_the_read_set_is_the_source_and_the_layer_and_nothing_else`, shown red by both plants
  in `test_the_read_set_check_fails_with_the_layer_missing_or_another_layer_added`;
- a layer offered in a list, to anyone: `test_a_layer_is_in_no_dataset_list_for_any_role`, shown
  red in `test_the_list_check_fails_with_layers_offered`;
- a layer chosen as a case's dataset or a composite's member, or a refusal that says one exists:
  `test_a_layer_cannot_be_chosen_and_is_refused_as_a_missing_dataset`;
- a layer's name taking a place in the unit's names, so a refused name would say a layer exists:
  `test_a_layers_name_takes_no_place_in_the_units_names`;
- a case reading two datasets: `test_a_case_reads_exactly_one_dataset`, shown red in
  `test_the_one_dataset_check_fails_with_the_check_removed`;
- a principal outside the case told more than of a missing case:
  `test_a_principal_outside_the_case_is_refused_as_for_a_missing_case`;
- a branch sharing its parent's layer: `test_a_branch_has_a_layer_of_its_own`;
- a layer stopping its case asking a hosted model: `test_a_layers_egress_is_its_sources`.

The Postgres half is `test_analyst_layer_store.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api import datasets as datasets_module
from services.api.app import app, get_audit, get_datasets, get_investigations, get_principal
from services.api.dataset_scope import scope_to_case
from services.api.datasets import (
    ANALYST_LAYER,
    Dataset,
    DatasetRefusedError,
    InMemoryDatasetStore,
)
from services.api.investigations import AccessLevel, Investigation, InvestigationNotFoundError

from schemas.domain import Principal

ALICE = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
BOB = Principal(id="bob", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
ADMIN = Principal(id="root", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
NO_ROLE = Principal(id="newcomer", clearance="OFFICIAL", org_unit="unit-1", roles=[])
#: Every kind of reader a list could be read by (ADR-099 Amendment 11 includes the role-less).
READERS = [ALICE, ADMIN, NO_ROLE]


def _dataset(dataset_id: str, unit: str, name: str) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=name,
        owning_unit=unit,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        created_by="seed",
    )


@pytest.fixture
def store() -> InMemoryDatasetStore:
    held = InMemoryDatasetStore()
    held.add(_dataset("enron", "unit-1", "Enron corpus"))
    held.add(_dataset("fixture", "unit-1", "Fixture Corp"))
    held.add(_dataset("theirs", "unit-2", "Another unit's"))
    return held


def assert_read_set(read: Sequence[str], *, source: Sequence[str], layer: str) -> None:
    """The one check every read-set test makes: the source (or a composite's members and its own
    id), then the case's own layer, and nothing else."""
    assert list(read) == [*source, layer]


# --- the read set -----------------------------------------------------------------------------


async def test_the_read_set_is_the_source_and_the_layer_and_nothing_else(
    store: InMemoryDatasetStore,
) -> None:
    await store.set_for_case("case-a", ["enron"], ALICE, case_name="Case A")
    await store.set_for_case("case-b", ["enron"], BOB, case_name="Case B")
    layer_a, layer_b = await store.layer_of_case("case-a"), await store.layer_of_case("case-b")
    assert layer_a and layer_b and layer_a != layer_b

    for case, layer in (("case-a", layer_a), ("case-b", layer_b)):
        assert_read_set(await store.ids_of_case(case), source=["enron"], layer=layer)
        # What the request's principal carries: the read set, through the one scoping call.
        scoped = await scope_to_case(ALICE, case, store)
        assert_read_set(scoped.datasets or [], source=["enron"], layer=layer)

    layer = store.datasets[layer_a]
    assert (layer.kind, layer.layer_of, layer.owning_unit) == (ANALYST_LAYER, "case-a", "unit-1")
    assert layer.name == "Analyst layer: Case A"


async def test_the_read_set_check_fails_with_the_layer_missing_or_another_layer_added(
    store: InMemoryDatasetStore,
) -> None:
    """Rule 15: the two wrong read sets, in the shape `ids_of_case` returns, are caught."""
    await store.set_for_case("case-a", ["enron"], ALICE)
    await store.set_for_case("case-b", ["enron"], BOB)
    layer_a = await store.layer_of_case("case-a")
    layer_b = await store.layer_of_case("case-b")
    assert layer_a and layer_b
    with pytest.raises(AssertionError):
        assert_read_set(["enron"], source=["enron"], layer=layer_a)
    with pytest.raises(AssertionError):
        assert_read_set(["enron", layer_a, layer_b], source=["enron"], layer=layer_a)


async def test_a_composite_case_reads_its_members_its_own_id_and_its_layer(
    store: InMemoryDatasetStore,
) -> None:
    both = await store.create_composite(ALICE, "Enron and Fixture", ["enron", "fixture"])
    await store.set_for_case("case-c", [both.id], ALICE)
    layer = await store.layer_of_case("case-c")
    assert layer
    assert_read_set(
        await store.ids_of_case("case-c"), source=["enron", "fixture", both.id], layer=layer
    )
    # A member-only case reads neither the other member nor the composite.
    await store.set_for_case("case-e", ["enron"], ALICE)
    assert "fixture" not in await store.ids_of_case("case-e")
    assert both.id not in await store.ids_of_case("case-e")


async def test_a_case_that_chose_nothing_reads_nothing(store: InMemoryDatasetStore) -> None:
    await store.ensure_layer("orphan", unit="unit-1", created_by="alice")
    assert await store.ids_of_case("orphan") == []


async def test_a_branch_has_a_layer_of_its_own(store: InMemoryDatasetStore) -> None:
    await store.set_for_case("parent", ["enron"], ALICE)
    await store.copy_case("parent", "branch")
    parent_layer = await store.layer_of_case("parent")
    branch_layer = await store.layer_of_case("branch")
    assert parent_layer and branch_layer and parent_layer != branch_layer
    assert_read_set(await store.ids_of_case("branch"), source=["enron"], layer=branch_layer)


# --- never offered ----------------------------------------------------------------------------


async def _listed_ids(store: InMemoryDatasetStore, case: str) -> set[str]:
    seen: set[str] = {d.id for d in await store.list_all()}
    for reader in READERS:
        seen |= {d.id for d in await store.list_for(reader)}
        seen |= {d.id for d in await store.of_case(case, reader)}
    return seen


async def test_a_layer_is_in_no_dataset_list_for_any_role(store: InMemoryDatasetStore) -> None:
    await store.set_for_case("case-a", ["enron"], ALICE)
    layer = await store.layer_of_case("case-a")
    assert layer and layer not in await _listed_ids(store, "case-a")


async def test_the_list_check_fails_with_layers_offered(
    store: InMemoryDatasetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: with the store's own filter gone (every dataset offered), the check sees it."""
    monkeypatch.setattr(InMemoryDatasetStore, "_offered", lambda self: list(self.datasets.values()))
    await store.set_for_case("case-a", ["enron"], ALICE)
    layer = await store.layer_of_case("case-a")
    assert layer in await _listed_ids(store, "case-a")


async def test_a_layer_cannot_be_chosen_and_is_refused_as_a_missing_dataset(
    store: InMemoryDatasetStore,
) -> None:
    await store.set_for_case("case-a", ["enron"], ALICE)
    layer = await store.layer_of_case("case-a")
    assert layer
    for named in (layer, "no-such-dataset"):
        with pytest.raises(DatasetRefusedError):
            await store.set_for_case("case-x", [named], ALICE)
        with pytest.raises(DatasetRefusedError):
            await store.create_composite(ALICE, f"With {named}", ["enron", named])
    assert await store.ids_of_case("case-x") == []


async def test_a_layers_name_takes_no_place_in_the_units_names(
    store: InMemoryDatasetStore,
) -> None:
    await store.set_for_case("case-a", ["enron"], ALICE, case_name="Shipping")
    layer = await store.layer_of_case("case-a")
    assert layer
    made = await store.create(ALICE, store.datasets[layer].name)
    assert made.name == store.datasets[layer].name


async def test_a_layers_egress_is_its_sources(store: InMemoryDatasetStore) -> None:
    await store.set_egress("enron", "contracted")
    await store.set_for_case("case-a", ["enron"], ALICE)
    layer = await store.layer_of_case("case-a")
    assert layer
    held = await store.egress_of(["enron", layer])
    assert held[layer].egress == "contracted"
    await store.set_egress("enron", "any")
    assert (await store.egress_of([layer]))[layer].egress == "any"


# --- one dataset per case -----------------------------------------------------------------------


async def test_a_case_reads_exactly_one_dataset(store: InMemoryDatasetStore) -> None:
    await store.set_for_case("case-a", ["enron"], ALICE)
    with pytest.raises(DatasetRefusedError):
        await store.set_for_case("case-a", ["enron", "fixture"], ALICE)
    assert await store.ids_of_case("case-a") == ["enron", await store.layer_of_case("case-a")]


async def test_the_one_dataset_check_fails_with_the_check_removed(
    store: InMemoryDatasetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: with `_one` replaced by the check it replaced (at least one), two are taken."""
    monkeypatch.setattr(datasets_module, "_one", lambda ids: datasets_module._ordered(ids)[0])
    await store.set_for_case("case-a", ["enron"], ALICE)
    with pytest.raises(pytest.fail.Exception), pytest.raises(DatasetRefusedError):
        await store.set_for_case("case-a", ["enron", "fixture"], ALICE)


# --- the routes -------------------------------------------------------------------------------


class _Investigations:
    """Cases with members: a principal holds a level only on the cases it is a member of."""

    def __init__(self) -> None:
        self.made: list[Investigation] = []
        self.members: dict[str, set[str]] = {}

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
        self.members[case.id] = {principal.id}
        return case

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        for case in self.made:
            if case.id == investigation_id and principal.id in self.members[case.id]:
                return case
        raise InvestigationNotFoundError(investigation_id)

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return [(c, AccessLevel.AUTHOR) for c in self.made if principal.id in self.members[c.id]]

    async def hidden_tab_ids(self, principal: Principal) -> set[str]:
        return set()


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


@pytest.fixture
def client(store: InMemoryDatasetStore):  # type: ignore[no-untyped-def]
    investigations = _Investigations()
    who = {"principal": ALICE}
    app.dependency_overrides[get_investigations] = lambda: investigations
    app.dependency_overrides[get_principal] = lambda: who["principal"]
    app.dependency_overrides[get_audit] = lambda: _Audit()
    app.dependency_overrides[get_datasets] = lambda: store
    yield TestClient(app, raise_server_exceptions=False), who
    app.dependency_overrides.clear()


def test_no_route_lists_a_layer(client, store: InMemoryDatasetStore) -> None:  # type: ignore[no-untyped-def]
    http, _ = client
    made = http.post("/v1/investigations", json={"name": "A", "dataset_ids": ["enron"]}).json()
    layer = store.datasets[next(i for i, d in store.datasets.items() if d.kind == ANALYST_LAYER)]
    assert layer.layer_of == made["id"]
    seen = str(http.get("/v1/datasets").json())
    seen += str(http.get(f"/v1/investigations/{made['id']}/datasets").json())
    seen += str(http.get("/v1/investigations").json())
    assert layer.id not in seen and layer.name not in seen


def test_a_layer_is_refused_at_the_route_as_a_missing_dataset(client, store) -> None:  # type: ignore[no-untyped-def]
    http, _ = client
    made = http.post("/v1/investigations", json={"name": "A", "dataset_ids": ["enron"]}).json()
    layer = next(i for i, d in store.datasets.items() if d.kind == ANALYST_LAYER)
    url = f"/v1/investigations/{made['id']}/datasets"
    as_layer = http.put(url, json={"dataset_ids": [layer]})
    as_missing = http.put(url, json={"dataset_ids": ["no-such-dataset"]})
    assert as_layer.status_code == 422
    assert (as_layer.status_code, as_layer.json()) == (as_missing.status_code, as_missing.json())
    made_over = http.post("/v1/investigations", json={"name": "B", "dataset_ids": [layer]})
    assert (made_over.status_code, made_over.json()) == (422, {"error": "dataset_refused"})


def test_a_case_made_over_two_datasets_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    http, _ = client
    refused = http.post(
        "/v1/investigations", json={"name": "Both", "dataset_ids": ["enron", "fixture"]}
    )
    assert (refused.status_code, refused.json()) == (422, {"error": "dataset_refused"})


def test_a_principal_outside_the_case_is_refused_as_for_a_missing_case(client) -> None:  # type: ignore[no-untyped-def]
    """ADR-099 decision 5: Bob is of the same unit and reads the same source dataset in a case of
    his own, but holds no level on Alice's case; he is told what he would be told of no case."""
    http, who = client
    alices = http.post("/v1/investigations", json={"name": "A", "dataset_ids": ["enron"]}).json()
    who["principal"] = BOB
    http.post("/v1/investigations", json={"name": "B", "dataset_ids": ["enron"]})
    outside = http.get(f"/v1/investigations/{alices['id']}/datasets")
    missing = http.get("/v1/investigations/no-such-case/datasets")
    assert outside.status_code == 404
    assert (outside.status_code, outside.json()) == (missing.status_code, missing.json())
    # A graph read under the case: refused before any read, exactly as for no case.
    outside = http.post(f"/v1/investigations/{alices['id']}/search", json={"query": "a"})
    missing = http.post("/v1/investigations/no-such-case/search", json={"query": "a"})
    assert outside.status_code == 404
    assert (outside.status_code, outside.json()) == (missing.status_code, missing.json())


def test_a_composite_is_made_of_the_units_sources_only(client, store) -> None:  # type: ignore[no-untyped-def]
    """ADR-099 Amendment 12 item 2: another unit's, a missing one and a layer are refused alike."""
    http, _ = client
    made = http.post(
        "/v1/datasets/composites", json={"name": "Both", "member_ids": ["enron", "fixture"]}
    )
    assert made.status_code == 201 and made.json()["members"] == ["enron", "fixture"]
    http.post("/v1/investigations", json={"name": "A", "dataset_ids": ["enron"]})
    layer = next(i for i, d in store.datasets.items() if d.kind == ANALYST_LAYER)
    answers = {
        member: http.post(
            "/v1/datasets/composites",
            json={"name": f"With {member}", "member_ids": ["enron", member]},
        )
        for member in ("theirs", "no-such-dataset", layer, made.json()["id"])
    }
    assert {(r.status_code, str(r.json())) for r in answers.values()} == {
        (422, str({"error": "dataset_refused"}))
    }
