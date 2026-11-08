"""ADR-143 decision 9 and ADR-090 Amendment 4 (L3.5): an analyst's own link type, proposed in a
case, usable at once there and nowhere else, decided on the Studio's *1 Model* tab of its dataset by a
holder of `accept_types`, and promotable into the dataset only once accepted and made live.

What a mistake would do, and the case that catches it (each shown red by a plant at its call site,
`process/lanes/case-b/L3.5_L3.7_RED_RECORD.md`):

- a proposed type's links promoted before a data engineer accepted it:
  `test_a_proposed_types_links_are_refused_promotion_until_accepted_and_live` (the
  service) and `test_the_promotable_route_refuses_then_allows` (the route, its first call site);
- a proposed type seen, used or withdrawn from another case reading the same dataset (rule 3):
  `test_a_proposed_type_is_visible_only_in_its_own_case` and its route twin;
- the Model tab's list read or decided outside the dataset, or without `accept_types` (rule 4):
  `test_the_model_tabs_proposals_are_the_datasets_alone_and_need_accept_types`;
- the proposer accepting their own: `test_the_proposer_cannot_accept_their_own`.

`inv-1` and `inv-2` both read the source dataset `ds-1`, each with its own analyst layer; `inv-3`
reads `ds-2`. A principal scoped to a case carries its read set (`app.get_principal`)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_datasets,
    get_investigations,
    get_link_types,
    get_ontology,
    get_principal,
    get_target_models,
)
from services.api.dataset_scope import set_case_datasets
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.link_type_store import ProposalNotFoundError
from services.api.link_types import (
    LinkTypeService,
    ProposalRefusedError,
    ProposalStatus,
)
from services.api.target_models import CORE_TYPES_FOR_TESTS, InMemoryTargetModelStore

from ontology.loader import load_default_ontology
from schemas.domain import Principal

from .test_investigation_access_routes import _Audit
from .test_link_type_service import Graph, MemoryStore, WorkingSet

LAYER = {"inv-1": "layer-1", "inv-2": "layer-2", "inv-3": "layer-3", "inv-4": "layer-4"}
SOURCE = {"inv-1": "ds-1", "inv-2": "ds-1", "inv-3": "ds-2", "inv-4": "ds-1"}


def _analyst(case: str, pid: str = "alice") -> Principal:
    return Principal(
        id=pid, clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"],
        datasets=[SOURCE[case], LAYER[case]],
    )  # fmt: skip


def _engineer(dataset: str = "ds-1", pid: str = "dan") -> Principal:
    return Principal(
        id=pid, clearance="OFFICIAL", org_unit="unit-1", roles=["data_engineer"], datasets=[dataset]
    )


class _Cases:
    """Three cases of unit-1; `levels` says who holds which level on each."""

    def __init__(self) -> None:
        self.cases = {
            c: Investigation(
                id=c, name=c, created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="alice",
                owning_unit="unit-1",
            )
            for c in ("inv-1", "inv-2", "inv-3", "inv-4")
        }  # fmt: skip
        self.levels: dict[tuple[str, str], AccessLevel] = {}

    async def get(self, investigation_id: str) -> Investigation:
        if investigation_id not in self.cases:
            raise InvestigationNotFoundError(investigation_id)
        return self.cases[investigation_id]

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        level = self.levels.get((investigation_id, principal.id))
        if level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError("too low")
        return await self.get(investigation_id)

    async def effective_level(self, investigation_id: str, principal: Principal) -> Any:
        return self.levels.get((investigation_id, principal.id))


class _Datasets:
    """What the dataset routes ask of the dataset store: nothing here is a composite or drawn."""

    async def composites_among(self, ids: Any) -> list[str]:
        return []

    async def egress_of(self, ids: Any) -> dict[str, Any]:
        return {}

    async def chosen_of_case(self, investigation_id: str) -> list[Any]:
        return []


async def _service() -> tuple[LinkTypeService, MemoryStore, InMemoryTargetModelStore, _Cases]:
    store, cases = MemoryStore(), _Cases()
    models = InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS)
    service = LinkTypeService(
        store, load_default_ontology(), Graph(), WorkingSet(), cases,  # type: ignore[arg-type]
        models=models,
    )  # fmt: skip
    await service.refresh()
    return service, store, models, cases


async def _propose(service: LinkTypeService, case: str = "inv-1", name: str = "BRIBED") -> Any:
    return await service.propose(
        case, _analyst(case), name=name, from_types=["Person"], to_types=["Person"],
        directed=True, colour=None, thickness=None, label=None,
        reason="Paid a prison officer to carry items in",
    )  # fmt: skip


async def _refusal(service: LinkTypeService, case: str, name: str = "BRIBED") -> str | None:
    found = await service.promotion_refusals(case, _analyst(case), [name])
    return found[name]


# --- the service ---------------------------------------------------------------------------------


async def test_a_proposal_names_its_cases_source_dataset_never_its_layer() -> None:
    """The request's read set may hold the layer first: the layer `dataset_scope` holds for the
    request is left out whatever its place."""
    service, _, _, _ = await _service()
    set_case_datasets(["layer-1", "ds-1"], layer="layer-1")
    try:
        p = await service.propose(
            "inv-1", _analyst("inv-1").model_copy(update={"datasets": ["layer-1", "ds-1"]}),
            name="BRIBED", from_types=["Person"], to_types=["Person"], directed=True, colour=None,
            thickness=None, label=None, reason="x",
        )  # fmt: skip
    finally:
        set_case_datasets(None)
    assert p.dataset_id == "ds-1"


async def test_a_proposed_type_is_visible_only_in_its_own_case() -> None:
    """Rule 3: `inv-2` reads the same dataset and learns nothing of `inv-1`'s proposal — not by the
    types it is offered, not by a withdrawal, not by a refused name, not by the promotion check."""
    service, store, _, _ = await _service()
    p = await _propose(service)
    assert "BRIBED" in await service.case_types("inv-1", _analyst("inv-1"))
    assert "BRIBED" not in await service.case_types("inv-2", _analyst("inv-2", "bob"))
    with pytest.raises(ProposalNotFoundError):
        await service.withdraw("inv-2", p.id, _analyst("inv-2"), reason="x", is_author=True)
    told = await _refusal(service, "inv-2")
    nothing = await _refusal(service, "inv-2", "NO_SUCH_TYPE")
    assert told is not None and nothing is not None
    assert told.replace("BRIBED", "X") == nothing.replace("NO_SUCH_TYPE", "X")
    # Proposing the same name there is not refused as "already proposed", which would tell.
    again = await _propose(service, case="inv-2")
    assert again.id != p.id and store.rows[p.id].status is ProposalStatus.PENDING


async def test_a_proposed_types_links_are_refused_promotion_until_accepted_and_live() -> (
    None
):
    service, _, models, _ = await _service()
    p = await _propose(service)
    pending = await _refusal(service, "inv-1")
    assert pending is not None and "not yet accepted" in pending
    accepted = await service.accept("ds-1", p.id, _engineer(), reason="Seen in three cases")
    assert accepted.status is ProposalStatus.ACCEPTED
    draft = await models.draft("ds-1")
    assert draft is not None
    added = [e for e in draft.extensions if e.name == "BRIBED"]
    assert [(e.kind, e.added_in) for e in added] == [("link_type", draft.version)]
    in_draft = await _refusal(service, "inv-1")
    assert in_draft is not None and f"version {draft.version}" in in_draft
    await models.make_live("ds-1", draft.version, _engineer())
    assert await _refusal(service, "inv-1") is None


async def test_an_accepted_type_once_live_is_offered_in_every_case_of_its_dataset() -> None:
    service, _, models, _ = await _service()
    p = await _propose(service)
    await service.accept("ds-1", p.id, _engineer(), reason="Useful")
    assert "BRIBED" not in await service.case_types("inv-2", _analyst("inv-2"))
    draft = await models.draft("ds-1")
    assert draft is not None
    await models.make_live("ds-1", draft.version, _engineer())
    offered = await service.case_types("inv-2", _analyst("inv-2"))
    assert "BRIBED" in offered and offered["BRIBED"].proposal_id is None
    assert "BRIBED" not in await service.case_types("inv-3", _analyst("inv-3"))


async def test_a_declined_types_links_stay_in_the_layer_for_good() -> None:
    service, _, _, _ = await _service()
    p = await _propose(service)
    with pytest.raises(ProposalRefusedError):  # a reason is required
        await service.decline("ds-1", p.id, _engineer(), reason=" ")
    declined = await service.decline("ds-1", p.id, _engineer(), reason="Use ASSOCIATE_OF")
    assert declined.status is ProposalStatus.REJECTED
    refused = await _refusal(service, "inv-1")
    assert refused is not None and "declined" in refused
    with pytest.raises(ProposalRefusedError):
        await service.accept("ds-1", p.id, _engineer(), reason="Changed my mind")


async def test_the_proposer_cannot_accept_their_own() -> None:
    """ADR-145 decision 7: a Super user holds both halves, never on their own work."""
    service, store, _, _ = await _service()
    p = await _propose(service)
    both = _engineer(pid="alice")
    with pytest.raises(ProposalRefusedError):
        await service.accept("ds-1", p.id, both, reason="Mine")
    assert store.rows[p.id].status is ProposalStatus.PENDING


async def test_another_datasets_proposal_is_not_found_on_this_datasets_tab() -> None:
    service, store, models, _ = await _service()
    p = await _propose(service, case="inv-3")
    with pytest.raises(ProposalNotFoundError):
        await service.accept("ds-1", p.id, _engineer(), reason="x")
    with pytest.raises(ProposalNotFoundError):
        await service.decline("ds-1", p.id, _engineer(), reason="x")
    assert [x.id for x in await service.dataset_proposals("ds-1")] == []
    assert store.rows[p.id].status is ProposalStatus.PENDING and await models.draft("ds-1") is None


async def test_accepting_merges_a_same_name_proposal_that_fits_and_leaves_one_that_does_not() -> (
    None
):
    service, store, _, _ = await _service()
    first = await _propose(service)
    fits = await _propose(service, case="inv-2")
    misfit = await service.propose(
        "inv-4", _analyst("inv-4", "bob"), name="BRIBED", from_types=["Person"],
        to_types=["Organisation"], directed=True, colour=None, thickness=None, label=None,
        reason="x",
    )  # fmt: skip
    await service.accept("ds-1", first.id, _engineer(), reason="Useful")
    assert store.rows[fits.id].status is ProposalStatus.MERGED
    assert store.rows[misfit.id].status is ProposalStatus.PENDING
    with pytest.raises(ProposalRefusedError):  # the name is in the model now
        await service.accept("ds-1", misfit.id, _engineer(), reason="x")


async def test_a_name_already_in_the_datasets_model_is_refused_at_proposal() -> None:
    service, _, _, _ = await _service()
    p = await _propose(service)
    await service.accept("ds-1", p.id, _engineer(), reason="Useful")
    with pytest.raises(ProposalRefusedError):
        await _propose(service, case="inv-2")


async def test_the_administrators_route_refuses_a_proposal_of_a_dataset() -> None:
    """ADR-090 Amendment 4: a proposal naming a dataset is decided on its Model tab, not by the
    deployment-wide promotion of ADR-090 decision 1."""
    service, store, _, _ = await _service()
    p = await _propose(service)
    admin = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
    with pytest.raises(ProposalRefusedError):
        await service.promote(p.id, admin, basis="probabilistic", reason="x")
    with pytest.raises(ProposalRefusedError):
        await service.reject(p.id, admin, reason="x")
    assert store.rows[p.id].status is ProposalStatus.PENDING


# --- the routes ----------------------------------------------------------------------------------


class _World:
    def __init__(self) -> None:
        self.service, self.store, self.models, self.cases = asyncio.run(_service())
        for case in ("inv-1", "inv-2", "inv-3"):
            self.cases.levels[(case, "alice")] = AccessLevel.EDITOR
        self.cases.levels[("inv-1", "bob")] = AccessLevel.VIEWER
        self.cases.levels[("inv-2", "bob")] = AccessLevel.EDITOR

    def client(self, principal: Principal) -> TestClient:
        app.dependency_overrides[get_investigations] = lambda: self.cases
        app.dependency_overrides[get_principal] = lambda: principal
        app.dependency_overrides[get_audit] = lambda: _Audit()
        app.dependency_overrides[get_link_types] = lambda: self.service
        app.dependency_overrides[get_ontology] = lambda: self.service._ontology  # noqa: SLF001
        app.dependency_overrides[get_target_models] = lambda: self.models
        app.dependency_overrides[get_datasets] = lambda: _Datasets()
        return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def world() -> Iterator[_World]:
    yield _World()
    app.dependency_overrides.clear()


PROPOSAL = {
    "name": "BRIBED",
    "from_types": ["Person"],
    "to_types": ["Person"],
    "directed": True,
    "reason": "Paid a prison officer to carry items in",
}


def _promotable(world: _World, case: str, who: str = "alice") -> dict[str, Any]:
    answer = world.client(_analyst(case, who)).post(
        f"/v1/investigations/{case}/link-types/promotable", json={"types": ["BRIBED"]}
    )
    assert answer.status_code == 200, answer.text
    return {t["name"]: t for t in answer.json()["types"]}["BRIBED"]


def test_the_promotable_route_refuses_then_allows(world: _World) -> None:
    made = world.client(_analyst("inv-1")).post(
        "/v1/investigations/inv-1/link-types", json=PROPOSAL
    )
    assert made.status_code == 200, made.text
    before = _promotable(world, "inv-1")
    assert before["promotable"] is False and "not yet accepted" in before["reason"]
    tab = world.client(_engineer())
    pid = made.json()["id"]
    done = tab.post(f"/v1/datasets/ds-1/model/proposals/{pid}/accept", json={"reason": "Useful"})
    assert done.status_code == 200, done.text and done.json()["status"] == "accepted"
    assert _promotable(world, "inv-1")["promotable"] is False  # in the draft, not yet live
    draft = asyncio.run(world.models.draft("ds-1"))
    assert draft is not None
    asyncio.run(world.models.make_live("ds-1", draft.version, _engineer()))
    after = _promotable(world, "inv-1")
    assert after["promotable"] is True and after["reason"] is None


def test_a_proposed_type_is_visible_only_in_its_own_case_through_the_routes(world: _World) -> None:
    made = world.client(_analyst("inv-1")).post(
        "/v1/investigations/inv-1/link-types", json=PROPOSAL
    )
    pid = made.json()["id"]
    bob = world.client(_analyst("inv-2", "bob"))  # the last client made: every call below is Bob's
    offered = bob.get("/v1/investigations/inv-2/link-types").json()["types"]
    assert "BRIBED" not in [t["definition"]["name"] for t in offered]
    withdraw = bob.post(f"/v1/investigations/inv-2/link-types/{pid}/withdraw", json={"reason": "x"})
    assert withdraw.status_code == 404
    assert _promotable(world, "inv-2", "bob")["promotable"] is False
    # Its reason is the one a name that does not exist gets.
    told = _promotable(world, "inv-2", "bob")["reason"]
    nothing = (
        world.client(_analyst("inv-2", "bob"))
        .post("/v1/investigations/inv-2/link-types/promotable", json={"types": ["NO_SUCH_TYPE"]})
        .json()["types"][0]["reason"]
    )
    assert told.replace("BRIBED", "X") == nothing.replace("NO_SUCH_TYPE", "X")


def test_the_model_tabs_proposals_are_the_datasets_alone_and_need_accept_types(
    world: _World,
) -> None:
    pid = (
        world.client(_analyst("inv-1"))
        .post("/v1/investigations/inv-1/link-types", json=PROPOSAL)
        .json()["id"]
    )
    world.client(_analyst("inv-3")).post(
        "/v1/investigations/inv-3/link-types", json={**PROPOSAL, "name": "SMUGGLED_FOR"}
    )
    listed = world.client(_engineer()).get("/v1/datasets/ds-1/model/proposals")
    assert listed.status_code == 200, listed.text
    rows = listed.json()["proposals"]
    assert [r["name"] for r in rows] == ["BRIBED"]
    # The tab names no case (rule 3): the data engineer may be a member of none.
    assert "investigation_id" not in rows[0] and "owning_unit" not in rows[0]
    # Outside the dataset: told it does not exist (404), for the list and both decisions. Each
    # client is made just before its call: the overrides are the app's, one principal at a time.
    outsider = _engineer("ds-2", "erin")
    assert world.client(outsider).get("/v1/datasets/ds-1/model/proposals").status_code == 404
    for act in ("accept", "decline"):
        url = f"/v1/datasets/ds-1/model/proposals/{pid}/{act}"
        assert world.client(outsider).post(url, json={"reason": "x"}).status_code == 404
        # Without `accept_types`: an analyst scoped to the dataset is refused (403).
        analyst = Principal(
            id="alice", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"],
            datasets=["ds-1"],
        )  # fmt: skip
        assert world.client(analyst).post(url, json={"reason": "x"}).status_code == 403
    assert (
        world.client(_engineer("ds-2"))
        .get("/v1/datasets/ds-2/model/proposals")
        .json()["proposals"][0]["name"]
        == "SMUGGLED_FOR"
    )
    assert world.store.rows[pid].status is ProposalStatus.PENDING
