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
- a case made from another holding a layer of its own, or one opened from an alert reading the
  original's: `test_a_case_made_from_another_holds_no_layer_of_its_own` and
  `test_a_case_opened_from_an_alert_keeps_an_empty_layer_of_its_own`, the second red with the
  original's layer linked (`test_the_jump_check_fails_with_the_originals_layer_linked`; the jump's
  real route is in `test_case_writes.py`, and writes into a layer read so are refused in
  `test_unconverted_case_layer.py`);
- a layer stopping its case asking a hosted model, or going further than its sources:
  `test_a_layers_egress_is_its_sources` and
  `test_a_composite_cases_layer_takes_the_strictest_of_members_that_differ`, shown red in
  `test_the_strictest_check_fails_with_the_loosest_planted`.

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

from .unconverted import made_before_l3_2

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
    """The one check every read-set test makes: the source (or a composite's own id and its
    members, ADR-099 Amendment 14), then the case's own layer, and nothing else."""
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


@pytest.mark.parametrize("defect", ["layer missing", "another case's layer added"])
async def test_the_read_set_check_fails_with_the_layer_missing_or_another_layer_added(
    store: InMemoryDatasetStore, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    """Rule 15: each defect planted in `datasets.read_set` itself, the function `ids_of_case` and
    so `scope_to_case` build the principal from, is caught by the check the test above makes."""
    await store.set_for_case("case-a", ["enron"], ALICE)
    await store.set_for_case("case-b", ["enron"], BOB)
    layer_a = await store.layer_of_case("case-a")
    layer_b = await store.layer_of_case("case-b")
    assert layer_a and layer_b
    real = datasets_module.read_set

    def planted(chosen: Sequence[Dataset], layer: str | None) -> list[str]:
        held = real(chosen, layer)
        if defect == "layer missing":
            return [d for d in held if d != layer]
        return [*held, layer_b if layer == layer_a else layer_a]

    monkeypatch.setattr(datasets_module, "read_set", planted)
    scoped = await scope_to_case(ALICE, "case-a", store)
    with pytest.raises(AssertionError):
        assert_read_set(scoped.datasets or [], source=["enron"], layer=layer_a)


async def test_a_composite_case_reads_its_own_id_its_members_and_its_layer(
    store: InMemoryDatasetStore,
) -> None:
    both = await store.create_composite(ALICE, "Enron and Fixture", ["enron", "fixture"])
    await store.set_for_case("case-c", [both.id], ALICE)
    layer = await store.layer_of_case("case-c")
    assert layer
    assert_read_set(
        await store.ids_of_case("case-c"), source=[both.id, "enron", "fixture"], layer=layer
    )
    # A member-only case reads neither the other member nor the composite.
    await store.set_for_case("case-e", ["enron"], ALICE)
    assert "fixture" not in await store.ids_of_case("case-e")
    assert both.id not in await store.ids_of_case("case-e")


async def test_a_case_that_chose_nothing_reads_nothing(store: InMemoryDatasetStore) -> None:
    await store.ensure_layer("orphan", unit="unit-1", created_by="alice")
    assert await store.ids_of_case("orphan") == []


async def _an_unconverted_case_and_a_jump(store: InMemoryDatasetStore) -> tuple[str | None, ...]:
    await store.set_for_case("parent", ["enron"], ALICE)
    await made_before_l3_2(store, "parent", "made")
    await store.read_the_same_dataset("parent", "jump", created_by=BOB.id)
    return tuple([await store.layer_of_case(c) for c in ("parent", "made", "jump")])


async def test_a_case_made_from_another_holds_no_layer_of_its_own(
    store: InMemoryDatasetStore,
) -> None:
    """ADR-144 Amendment 1 decision 2: a case made from another since L3.1, until the upgrade turns
    it into a view, holds no layer; it reads its original case's dataset and layer, the layer
    read-only."""
    parent, made, _jump = await _an_unconverted_case_and_a_jump(store)
    assert parent is not None and made is None
    assert await store.read_only_layer_of("made") == parent
    assert_read_set(await store.ids_of_case("made"), source=["enron"], layer=parent)


async def test_a_case_opened_from_an_alert_keeps_an_empty_layer_of_its_own(
    store: InMemoryDatasetStore,
) -> None:
    """The exception (ADR-143 Amendment 1 item 3): the jumper may hold no level on the alert's
    case, so the case opened from it reads the dataset alone and has a layer of its own."""
    parent, _made, jump = await _an_unconverted_case_and_a_jump(store)
    assert jump is not None and jump != parent
    assert await store.read_only_layer_of("jump") is None
    assert_read_set(await store.ids_of_case("jump"), source=["enron"], layer=jump)
    assert store.datasets[jump].created_by == BOB.id


async def test_the_jump_check_fails_with_the_originals_layer_linked(
    store: InMemoryDatasetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: `read_the_same_dataset` planted to link the new case to the original's layer,
    as the old copy did, and the alert's case reads a layer its maker may hold no level on."""

    async def linked(self: InMemoryDatasetStore, original: str, made: str, **_: object) -> None:
        await made_before_l3_2(self, original, made)

    monkeypatch.setattr(InMemoryDatasetStore, "read_the_same_dataset", linked)
    parent, _made, jump = await _an_unconverted_case_and_a_jump(store)
    assert jump is None and await store.read_only_layer_of("jump") == parent


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


async def _composite_layer_egress(store: InMemoryDatasetStore) -> Dataset:
    """A composite case whose members differ (`any` and `contracted`), the composite itself set to
    `any` by an administrator: its layer's egress, as an egress question sees it."""
    both = await store.create_composite(ALICE, "Both", ["enron", "fixture"])
    await store.set_egress("enron", "any")
    await store.set_egress("fixture", "contracted")
    await store.set_egress(both.id, "any")
    await store.set_for_case("case-c", [both.id], ALICE)
    layer = await store.layer_of_case("case-c")
    assert layer
    return (await store.egress_of([layer]))[layer]


async def test_a_composite_cases_layer_takes_the_strictest_of_members_that_differ(
    store: InMemoryDatasetStore,
) -> None:
    """ADR-136 Amendment 1: the strictest of everything else the case reads, the composite's own id
    and each member alike, under the name of the dataset it takes that from."""
    held = await _composite_layer_egress(store)
    assert held.egress == "contracted"
    assert held.name == store.datasets["fixture"].name


async def test_the_strictest_check_fails_with_the_loosest_planted(
    store: InMemoryDatasetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: `strictest_egress` turned to the loosest (max for min), at its one definition."""
    order = datasets_module._EGRESS_ORDER
    monkeypatch.setattr(
        datasets_module,
        "strictest_egress",
        lambda egresses: max(egresses, key=order.__getitem__, default="none"),
    )
    assert (await _composite_layer_egress(store)).egress != "contracted"


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
        domains: list[str] | None = None,
    ) -> Investigation:
        case = Investigation(
            id=f"case-{len(self.made) + 1}",
            name=name,
            created_at=datetime.now(UTC),
            created_by=principal.id,
            owning_unit=principal.org_unit,
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
    http, who = client
    made = http.post("/v1/investigations", json={"name": "A", "dataset_ids": ["enron"]}).json()
    layer = store.datasets[next(i for i, d in store.datasets.items() if d.kind == ANALYST_LAYER)]
    assert layer.layer_of == made["id"]
    seen = ""
    for reader in READERS:  # an analyst, an administrator, and someone holding no role
        who["principal"] = reader.model_copy(update={"id": "alice"})  # Alice's own case
        seen += str(http.get("/v1/datasets").json())
        seen += str(http.get(f"/v1/investigations/{made['id']}/datasets").json())
        seen += str(http.get("/v1/investigations").json())
        seen += str(http.get("/v1/admin/datasets").json())
    assert layer.id not in seen and layer.name not in seen
    # ... and the administrator's list did answer (so the check above looked at something).
    who["principal"] = ADMIN
    assert http.get("/v1/admin/datasets").status_code == 200


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


async def test_a_refusal_to_send_names_the_source_never_the_layer(
    store: InMemoryDatasetStore,
) -> None:
    """ADR-136 and ADR-143 decision 1: a model request carries the case's read set, layer included;
    the refusal names the source once and never the layer, and its verdict is the source's."""
    from services.api.model_routing import Engine, dataset_refusal

    await store.set_for_case("case-a", ["enron"], ALICE, case_name="Shipping")
    reads = await store.ids_of_case("case-a")
    engine = Engine(
        name="hosted", label="Hosted", models={}, key_present=True, privacy_contract=False
    )
    refusal = dataset_refusal(engine, reads, await store.egress_of(reads))
    assert refusal is not None
    assert refusal.startswith("“Enron corpus” is set to egress none")
    assert "Analyst layer" not in refusal and "Shipping" not in refusal
    await store.set_egress("enron", "any")
    assert dataset_refusal(engine, reads, await store.egress_of(reads)) is None
