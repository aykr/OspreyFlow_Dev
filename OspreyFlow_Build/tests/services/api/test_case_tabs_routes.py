"""Case tabs: the tab strip's open-or-hidden flag (ADR-084).

Whether a case's tab is open or hidden is a flag per analyst, so one analyst closing a tab never
closes it for anyone else who can see the case. (The tabs once also held branches of a case; no
case is made from another since L3.2, ADR-144 Amendment 1.)

What a mistake here would do, and the case that catches it:

- an open/hidden flag shared between analysts would hide a tab from the wrong person
  (`test_hiding_a_tab_hides_it_for_that_analyst_only`);
- a flag settable on a case the account cannot see would confirm the case exists
  (`test_the_tab_flag_of_a_case_in_another_unit_answers_not_found`).

Route levels are in `test_investigation_levels.py`'s table; this file is behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_history,
    get_investigations,
    get_principal,
    get_valkey,
    get_working_set,
)
from services.api.investigations import (
    AccessLevel,
    Investigation,
    InvestigationNotFoundError,
)

from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

ALICE = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
BOB = Principal(id="bob", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
OTHER_UNIT = Principal(id="carol", clearance="OFFICIAL", org_unit="unit-2", roles=["analyst"])


def _node(node_id: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1"),
    )


class _FakeWorkingSet:
    async def current_membership(self, investigation_id: str) -> tuple[list[Node], list[Edge]]:
        return [], []


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _FakeHistory:
    async def record_step(self, investigation_id: str, **kwargs: object) -> object:
        return object()


class _FakeValkey:
    async def publish(self, channel: str, message: str) -> int:
        return 1


class _FakeInvestigations:
    """Holds the cases by id, and one hidden-tab set per account, as the real store does."""

    def __init__(self) -> None:
        self.cases: dict[str, Investigation] = {}
        self.hidden: dict[str, set[str]] = {}
        self.created: list[Investigation] = []
        #: What each `create` was given for `domains`; None is NULL, "never chosen".
        self.asked_domains: list[list[str] | None] = []
        self._next = 1
        self.add("inv-1", "Fixture Corp", owner=ALICE)

    def add(
        self,
        case_id: str,
        name: str,
        *,
        owner: Principal,
        domains: list[str] | None = None,
    ) -> Investigation:
        case = Investigation(
            id=case_id,
            name=name,
            created_at=datetime(2026, 1, self._next, tzinfo=UTC),
            created_by=owner.id,
            owning_unit=owner.org_unit,
            domains=domains or [],  # type: ignore[arg-type]
            domains_chosen=domains is not None,
        )
        self._next += 1
        self.cases[case_id] = case
        return case

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        case = self.cases.get(investigation_id)
        if case is None or case.owning_unit != principal.org_unit:
            raise InvestigationNotFoundError(investigation_id)
        return case

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return [
            (case, AccessLevel.AUTHOR)
            for case in self.cases.values()
            if case.owning_unit == principal.org_unit
        ]

    async def hidden_tab_ids(self, principal: Principal) -> set[str]:
        return set(self.hidden.get(principal.id, set()))

    async def set_tab_hidden(
        self, principal: Principal, investigation_id: str, hidden: bool
    ) -> None:
        marks = self.hidden.setdefault(principal.id, set())
        if hidden:
            marks.add(investigation_id)
        else:
            marks.discard(investigation_id)


@pytest.fixture
def client() -> TestClient:
    working_set = _FakeWorkingSet()
    investigations = _FakeInvestigations()
    audit = _FakeAudit()
    app.dependency_overrides[get_principal] = lambda: ALICE
    app.dependency_overrides[get_working_set] = lambda: working_set
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = lambda: investigations
    app.dependency_overrides[get_history] = lambda: _FakeHistory()
    app.dependency_overrides[get_valkey] = lambda: _FakeValkey()
    test_client = TestClient(app)
    test_client.working_set = working_set  # type: ignore[attr-defined]
    test_client.investigations = investigations  # type: ignore[attr-defined]
    test_client.audit = audit  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def _as(principal: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: principal


def _listing(client: TestClient) -> dict[str, dict[str, object]]:
    return {entry["id"]: entry for entry in client.get("/v1/investigations").json()}


def test_a_listed_case_says_whether_its_tab_is_hidden_and_defaults_to_not(
    client: TestClient,
) -> None:
    listed = _listing(client)

    assert listed["inv-1"]["tab_hidden"] is False


def test_hiding_a_tab_hides_it_for_that_analyst_only(client: TestClient) -> None:
    """Catches a flag stored on the case instead of per account: Alice closing a tab would close it
    for Bob as well."""
    assert client.put("/v1/investigations/inv-1/tab", json={"hidden": True}).status_code == 204
    assert _listing(client)["inv-1"]["tab_hidden"] is True

    _as(BOB)
    assert _listing(client)["inv-1"]["tab_hidden"] is False


def test_a_hidden_tab_can_be_brought_back(client: TestClient) -> None:
    client.put("/v1/investigations/inv-1/tab", json={"hidden": True})
    client.put("/v1/investigations/inv-1/tab", json={"hidden": False})

    assert _listing(client)["inv-1"]["tab_hidden"] is False


def test_the_tab_flag_of_a_case_in_another_unit_answers_not_found(client: TestClient) -> None:
    """Rule 4 for this path: an account that cannot see a case must not be able to tell it exists
    by setting a flag on it."""
    _as(OTHER_UNIT)
    response = client.put("/v1/investigations/inv-1/tab", json={"hidden": True})

    assert response.status_code == 404
    assert client.investigations.hidden == {}  # type: ignore[attr-defined]


def test_the_tab_flag_needs_a_yes_or_no(client: TestClient) -> None:
    assert client.put("/v1/investigations/inv-1/tab", json={}).status_code == 422
    assert client.put("/v1/investigations/inv-1/tab", json={"hidden": "maybe"}).status_code == 422
