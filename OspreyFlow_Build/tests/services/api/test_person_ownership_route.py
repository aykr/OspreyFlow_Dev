"""`GET /v1/admin/people/{user_id}/ownership` (ADR-145 decision 6 and A4; L3.8): what a person owns
that the case lane keeps, read by an administrator who may disable people and by no one else. The
real app and `require_right` run; the store is a stand-in that refuses as the real one does (rule
15): its one item, a link-type proposal in unit-1's case on a SECRET dataset, goes only to an
administrator of unit-1 cleared to SECRET, as the real store's reads give it; anyone else is answered
nothing and told some are withheld. It
records the unit and clearance it was asked with, so the route is shown to pass the administrator's
own (`test_person_ownership_store.py` runs the real SQL under the lease).

What a mistake would do, and the case that catches it (each shown red with its check removed,
`process/lanes/case-b/L3.8_RED_RECORD.md`):

- the route answered without `manage_people`: `test_everyone_without_manage_people_is_refused`;
- the store asked with someone else's unit or clearance than the administrator's own:
  `test_the_store_is_asked_with_the_administrators_own_unit_and_clearance` and
  `test_another_units_or_a_lower_cleared_administrator_is_told_only_that_some_are_withheld`;
- the read not audited: `test_the_read_is_audited_with_its_count`.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app
from services.api.person_ownership import PROMOTION_KINDS

from ontology.handling import HandlingScheme, load_uk_le_scheme
from schemas.domain import Principal
from schemas.person_ownership import OwnershipItem, PersonOwnership

TOKENS: dict[str, Principal] = {
    "adm-1": Principal(id="adm-1", clearance="SECRET", org_unit="unit-1", roles=["osprey-admin"]),
    "ppl-1": Principal(
        id="ppl-1", clearance="OFFICIAL", org_unit="unit-2", roles=["right:manage_people"]
    ),  # fmt: skip
    "adm-low": Principal(
        id="adm-low", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"]
    ),
    "ana-1": Principal(id="ana-1", clearance="SECRET", org_unit="unit-1", roles=["analyst"]),
    "eng-1": Principal(id="eng-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]),
    "rv-1": Principal(id="rv-1", clearance="SECRET", org_unit="unit-1", roles=["reports_viewer"]),
    "su-1": Principal(
        id="su-1",
        clearance="SECRET",
        org_unit="unit-1",
        roles=["analyst", "data_engineer", "reports_viewer"],
    ),  # fmt: skip
}


PROPOSAL_LABEL = "A proposed link type in the case Kestrel, waiting for a decision"


class _Resolver:
    async def resolve_principal(self, token: str) -> Principal:
        return self.resolve(token)

    def resolve(self, token: str) -> Principal:
        return TOKENS[token]


class _Roles:
    async def current_rights(self, ids: Any = None) -> dict[str, frozenset[Any]]:
        return {}


class _Ownership:
    """`PostgresOwnershipStore`'s shape, refusing what it refuses: the item is unit-1's, at SECRET."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str | None, str]] = []

    async def owned_by(
        self, person: str, *, admin: Principal, scheme: HandlingScheme
    ) -> PersonOwnership:
        self.asked.append((person, admin.org_unit, admin.clearance))
        if admin.org_unit != "unit-1" or not scheme.clears(admin.clearance, "SECRET"):
            return PersonOwnership(person=person, withheld=True,
                                   not_yet_listed=list(PROMOTION_KINDS))  # fmt: skip
        items = [OwnershipItem(kind="link_type_proposal", id="p-1", investigation_id="c-k",
                               label=PROPOSAL_LABEL)]  # fmt: skip
        return PersonOwnership(person=person, items=items, counts={"link_type_proposal": 1},
                               not_yet_listed=list(PROMOTION_KINDS))  # fmt: skip


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    ownership, audit = _Ownership(), _Audit()
    state = {"principal_resolver": _Resolver(), "custom_roles": _Roles(), "ownership": ownership,
             "audit": audit, "handling_scheme": load_uk_le_scheme()}  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(client=TestClient(app), ownership=ownership, audit=audit)


def _get(world: SimpleNamespace, who: str, person: str = "ana-2") -> Any:
    return world.client.get(
        f"/v1/admin/people/{person}/ownership", headers={"Authorization": f"Bearer {who}"}
    )


@pytest.mark.parametrize("who", ["ana-1", "eng-1", "rv-1", "su-1"])
def test_everyone_without_manage_people_is_refused(world: SimpleNamespace, who: str) -> None:
    answer = _get(world, who)
    assert answer.status_code == 403, answer.text
    assert answer.json()["detail"] == {"error": "right_required", "right": "manage_people"}
    assert world.ownership.asked == [] and world.audit.entries == []


def test_a_person_with_no_token_is_refused(world: SimpleNamespace) -> None:
    assert world.client.get("/v1/admin/people/ana-2/ownership").status_code == 401
    assert world.ownership.asked == []


def test_the_store_is_asked_with_the_administrators_own_unit_and_clearance(
    world: SimpleNamespace,
) -> None:
    answer = _get(world, "adm-1")
    assert answer.status_code == 200, answer.text
    assert world.ownership.asked == [("ana-2", "unit-1", "SECRET")]
    body = answer.json()
    assert body["person"] == "ana-2"
    assert body["items"] == [{"kind": "link_type_proposal", "id": "p-1", "investigation_id": "c-k",
                              "label": PROPOSAL_LABEL}]  # fmt: skip
    assert body["counts"] == {"link_type_proposal": 1} and body["withheld"] is False
    assert body["not_yet_listed"] == list(PROMOTION_KINDS)


@pytest.mark.parametrize("who", ["ppl-1", "adm-low"])
def test_another_units_or_a_lower_cleared_administrator_is_told_only_that_some_are_withheld(
    world: SimpleNamespace, who: str
) -> None:
    answer = _get(world, who)
    assert answer.status_code == 200, answer.text
    held = TOKENS[who]
    assert world.ownership.asked == [("ana-2", held.org_unit, held.clearance)]
    body = answer.json()
    assert body["items"] == [] and body["counts"] == {} and body["withheld"] is True
    assert "p-1" not in answer.text and "Kestrel" not in answer.text and "c-k" not in answer.text


def test_the_read_is_audited_with_its_count(world: SimpleNamespace) -> None:
    _get(world, "adm-1")
    [entry] = world.audit.entries
    assert entry["action"] == "read_person_ownership"
    assert entry["principal"].id == "adm-1"
    assert entry["resolved_query"] == {"user_id": "ana-2", "items": 1}
    assert entry["result_cardinality"] == 1
