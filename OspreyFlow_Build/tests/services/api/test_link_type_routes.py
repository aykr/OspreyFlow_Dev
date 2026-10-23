"""ADR-090's routes: who may propose, read, withdraw and decide, and what `/v1/ontology` shows. The
case level is `_authorized_at`'s (`test_investigation_levels.py` holds the table); here, that the
levels and the administrator's role hold end to end, that another unit's administrator is told
nothing, and that a proposal's own label is never sent to the Glass (rule 7)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_investigations,
    get_link_types,
    get_ontology,
    get_principal,
)
from services.api.investigations import AccessLevel, Investigation, InvestigationNotFoundError
from services.api.link_types import LinkTypeService

from ontology.loader import load_default_ontology
from schemas.domain import Principal

from .test_investigation_access_routes import _Audit, _Store
from .test_link_type_service import Graph, MemoryStore, WorkingSet

ALICE = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
BOB = Principal(id="bob", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
OTHER_ADMIN = Principal(
    id="admin-9", clearance="OFFICIAL", org_unit="unit-9", roles=["osprey-admin"]
)


class _Cases(_Store):
    async def get(self, investigation_id: str) -> Investigation:
        if investigation_id != "inv-1":
            raise InvestigationNotFoundError(investigation_id)
        return self.case


class _World:
    def __init__(self) -> None:
        self.cases = _Cases()
        self.cases.grants["bob"] = AccessLevel.VIEWER
        # The core, carrying a pack version without composing any pack's types in.
        self.ontology = load_default_ontology().model_copy(update={"packs": {"niem": 3}})
        self.store = MemoryStore()
        self.service = LinkTypeService(
            self.store,
            self.ontology,
            Graph(),
            WorkingSet(),
            self.cases,  # type: ignore[arg-type]
        )
        asyncio.run(self.service.refresh())

    def client(self, principal: Principal) -> TestClient:
        app.dependency_overrides[get_investigations] = lambda: self.cases
        app.dependency_overrides[get_principal] = lambda: principal
        app.dependency_overrides[get_audit] = lambda: _Audit()
        app.dependency_overrides[get_link_types] = lambda: self.service
        app.dependency_overrides[get_ontology] = lambda: self.ontology
        return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def world() -> Iterator[_World]:
    yield _World()
    app.dependency_overrides.clear()


PROPOSAL = {
    "name": "KNOWN_TO",
    "from_types": ["Person"],
    "to_types": ["Person"],
    "directed": False,
    "reason": "They know each other by sight",
}


def test_an_editor_proposes_and_the_case_offers_it_marked_as_proposed(world: _World) -> None:
    made = world.client(ALICE).post("/v1/investigations/inv-1/link-types", json=PROPOSAL)
    assert made.status_code == 200, made.text
    offered = world.client(BOB).get("/v1/investigations/inv-1/link-types").json()["types"]
    known = [t for t in offered if t["definition"]["name"] == "KNOWN_TO"]
    assert len(known) == 1 and known[0]["proposal_id"] == made.json()["id"]
    assert all("__" not in t["definition"]["name"] for t in offered)


def test_a_viewer_cannot_propose_and_a_stranger_cannot_tell_the_case_exists(world: _World) -> None:
    assert (
        world.client(BOB).post("/v1/investigations/inv-1/link-types", json=PROPOSAL).status_code
        == 403
    )
    stranger = Principal(id="eve", clearance="OFFICIAL", org_unit="unit-2", roles=["analyst"])
    assert world.client(stranger).get("/v1/investigations/inv-1/link-types").status_code == 404
    assert world.store.rows == {}


def test_a_refused_name_says_why(world: _World) -> None:
    refused = world.client(ALICE).post(
        "/v1/investigations/inv-1/link-types", json={**PROPOSAL, "name": "ASSOCIATE_OF"}
    )
    assert refused.status_code == 422 and refused.json()["error"] == "proposal_refused"


def test_only_an_administrator_of_the_unit_lists_and_decides(world: _World) -> None:
    pid = (
        world.client(ALICE).post("/v1/investigations/inv-1/link-types", json=PROPOSAL).json()["id"]
    )
    assert world.client(ALICE).get("/v1/admin/link-types").status_code == 403
    assert world.client(OTHER_ADMIN).get("/v1/admin/link-types").json() == {"proposals": []}
    promote = {"basis": "direct", "reason": "A loader backs it"}
    assert (
        world.client(OTHER_ADMIN)
        .post(f"/v1/admin/link-types/{pid}/promote", json=promote)
        .status_code
        == 404
    )
    assert (
        world.client(ALICE).post(f"/v1/admin/link-types/{pid}/promote", json=promote).status_code
        == 403
    )
    listed = world.client(ADMIN).get("/v1/admin/link-types").json()["proposals"]
    assert [p["id"] for p in listed] == [pid]
    done = world.client(ADMIN).post(f"/v1/admin/link-types/{pid}/promote", json=promote)
    assert done.status_code == 200 and done.json()["status"] == "promoted"


def test_the_ontology_route_shows_a_promoted_type_and_never_a_proposals_label(
    world: _World,
) -> None:
    pid = (
        world.client(ALICE).post("/v1/investigations/inv-1/link-types", json=PROPOSAL).json()["id"]
    )
    before = world.client(BOB).get("/v1/ontology").json()
    assert (
        all("__" not in t["name"] for t in before["edge_types"]) and before["storage_aliases"] == {}
    )
    world.client(ADMIN).post(
        f"/v1/admin/link-types/{pid}/promote", json={"basis": "probabilistic", "reason": "Useful"}
    )
    after = world.client(BOB).get("/v1/ontology").json()
    assert "KNOWN_TO" in [t["name"] for t in after["edge_types"]]
    assert after["overlay_revision"] == 1 and after["version"] == before["version"]
    # The world carries {"niem": 3}, so a route or overlay refresh that empties packs fails.
    assert "packs" in after and after["packs"] == world.ontology.packs


def test_the_proposer_withdraws_but_another_viewer_cannot(world: _World) -> None:
    pid = (
        world.client(ALICE).post("/v1/investigations/inv-1/link-types", json=PROPOSAL).json()["id"]
    )
    body = {"reason": "Not needed"}
    assert (
        world.client(BOB)
        .post(f"/v1/investigations/inv-1/link-types/{pid}/withdraw", json=body)
        .status_code
        == 403
    )
    done = world.client(ALICE).post(
        f"/v1/investigations/inv-1/link-types/{pid}/withdraw", json=body
    )
    assert done.status_code == 200 and done.json()["status"] == "withdrawn"
