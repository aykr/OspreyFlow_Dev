"""Branch tabs: the routes behind "Branch selected" and the tab strip (ADR-084).

A tab is a saved branch of a case: a case of its own that the branching analyst owns, holding the
chosen nodes and the links between them. Whether a tab is open or hidden is a flag per analyst, so
one analyst closing a tab never closes it for anyone else who can see the case.

What a mistake here would do, and the case that catches it:

- a branch of a chosen set that ignored the choice would copy the whole working set
  (`test_a_branch_of_a_choice_passes_the_choice_to_the_service`);
- a refused choice that left an empty case behind would clutter the analyst's list
  (`test_a_choice_with_nothing_to_copy_is_a_422_and_creates_no_case`);
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
    get_analytics,
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
from services.api.working_set.models import DeltaAdd, ExpansionOutcome, NothingToBranchError

from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Interval,
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
    def __init__(self) -> None:
        self.contents_calls: list[list[str] | None] = []
        self.branch_calls: list[tuple[str, str, list[str] | None]] = []

    async def branch_contents(
        self, source: str, principal: Principal, node_ids: list[str] | None = None
    ) -> tuple[list[Node], list[Edge], int]:
        self.contents_calls.append(node_ids)
        if node_ids is None:
            return [_node("a"), _node("b"), _node("c")], [], 0
        present = [n for n in node_ids if n in {"a", "b", "c"}]
        if not present:
            raise NothingToBranchError
        return [_node(n) for n in present], [], 0

    async def branch(
        self,
        source: str,
        new: str,
        principal: Principal,
        node_ids: list[str] | None = None,
    ) -> ExpansionOutcome:
        self.branch_calls.append((source, new, node_ids))
        nodes, edges, _ = await self.branch_contents(source, principal, node_ids)
        return ExpansionOutcome(delta=DeltaAdd(seq=1, nodes=nodes, edges=edges))

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
        branched_from: str | None = None,
        domains: list[str] | None = None,
    ) -> Investigation:
        case = Investigation(
            id=case_id,
            name=name,
            created_at=datetime(2026, 1, self._next, tzinfo=UTC),
            created_by=owner.id,
            owning_unit=owner.org_unit,
            branched_from=branched_from,
            domains=domains or [],  # type: ignore[arg-type]
            domains_chosen=domains is not None,
        )
        self._next += 1
        self.cases[case_id] = case
        return case

    async def create(
        self,
        principal: Principal,
        *,
        name: str,
        branched_from: str | None = None,
        domains: list[str] | None = None,
        branch_window: Interval | None = None,
    ) -> Investigation:
        self.asked_domains.append(None if domains is None else list(domains))
        case = self.add(
            f"branch-{len(self.created) + 1}",
            name,
            owner=principal,
            branched_from=branched_from,
            domains=domains,
        )
        case.branch_window = branch_window
        self.created.append(case)
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


class _NoAnalytics:
    """A branch with no window asks analytics nothing (ADR-128 decision 2): any call fails."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"a branch with no window asked analytics for {name}")


@pytest.fixture
def client() -> TestClient:
    working_set = _FakeWorkingSet()
    investigations = _FakeInvestigations()
    audit = _FakeAudit()
    app.dependency_overrides[get_principal] = lambda: ALICE
    app.dependency_overrides[get_working_set] = lambda: working_set
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_analytics] = lambda: _NoAnalytics()
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


# --- branching a chosen set -------------------------------------------------------------------


def test_a_branch_of_a_choice_passes_the_choice_to_the_service(client: TestClient) -> None:
    response = client.post("/v1/investigations/inv-1/branch", json={"node_ids": ["a", "b"]})

    assert response.status_code == 201
    body = response.json()
    assert body["branched_from"] == "inv-1"
    assert body["created_by"] == "alice"
    # ADR-097: a fact about the branch, not a selection count, and no middle dot (review item 3).
    assert body["name"] == "Branch of Fixture Corp (2 nodes)"
    assert client.working_set.branch_calls == [("inv-1", body["id"], ["a", "b"])]  # type: ignore[attr-defined]


def test_a_branch_takes_its_parents_domain_packs(client: TestClient) -> None:
    """ADR-126 decision 1: a branch is the same kind of case as the one it was made from. The
    parent here holds two packs; a branch route that did not pass them on would read as POLE."""
    investigations = client.investigations  # type: ignore[attr-defined]
    investigations.add("inv-2", "Mixed case", owner=ALICE, domains=["fibo", "niem"])

    whole = client.post("/v1/investigations/inv-2/branch")
    chosen = client.post("/v1/investigations/inv-2/branch", json={"node_ids": ["a"]})

    assert whole.status_code == chosen.status_code == 201
    assert whole.json()["domains"] == ["fibo", "niem"]
    assert chosen.json()["domains"] == ["fibo", "niem"]
    plain = client.post("/v1/investigations/inv-1/branch")
    assert plain.json()["domains"] == [], "a parent that reads as POLE passes on POLE"


def test_a_branch_inherits_the_stored_value_exactly(client: TestClient) -> None:
    """ADR-126 decision 2: a branch of a never-chosen parent (NULL) is never chosen, and one of a
    parent chosen as POLE (`{}`) is `{}`. The read-side list is `[]` for both."""
    investigations = client.investigations  # type: ignore[attr-defined]
    investigations.add("unchosen", "Never chosen", owner=ALICE, domains=None)
    investigations.add("pole", "Chosen POLE", owner=ALICE, domains=[])
    investigations.add("mixed", "Mixed", owner=ALICE, domains=["niem"])

    for case in ("unchosen", "pole", "mixed"):
        assert client.post(f"/v1/investigations/{case}/branch").status_code == 201

    assert investigations.asked_domains == [None, [], ["niem"]]


def test_a_branch_with_no_body_still_forks_the_whole_working_set(client: TestClient) -> None:
    """The route existed before choices did (a cap breach's "branch" option); it must not change."""
    response = client.post("/v1/investigations/inv-1/branch")

    assert response.status_code == 201
    assert response.json()["name"] == "Branch of Fixture Corp"
    assert client.working_set.branch_calls[0][2] is None  # type: ignore[attr-defined]


def test_a_name_in_the_request_is_the_name_of_the_branch(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations/inv-1/branch", json={"node_ids": ["a"], "name": "  The Volkovs  "}
    )

    assert response.status_code == 201
    assert response.json()["name"] == "The Volkovs"


def test_a_choice_with_nothing_to_copy_is_a_422_and_creates_no_case(client: TestClient) -> None:
    """The same answer whether the ids are hidden or do not exist (the service raises one error for
    both), and no empty case is left in the analyst's list."""
    response = client.post("/v1/investigations/inv-1/branch", json={"node_ids": ["ghost"]})

    assert response.status_code == 422
    assert response.json()["error"] == "nothing_to_branch"
    assert client.investigations.created == []  # type: ignore[attr-defined]
    assert client.working_set.branch_calls == []  # type: ignore[attr-defined]


def test_an_empty_choice_is_refused_like_any_other_that_leaves_nothing(client: TestClient) -> None:
    response = client.post("/v1/investigations/inv-1/branch", json={"node_ids": []})

    assert response.status_code == 422
    assert client.investigations.created == []  # type: ignore[attr-defined]


def test_a_branch_of_a_choice_is_audited_with_what_was_chosen(client: TestClient) -> None:
    client.post("/v1/investigations/inv-1/branch", json={"node_ids": ["a", "b"]})

    (record,) = [r for r in client.audit.records if r["action"] == "branch"]  # type: ignore[attr-defined]
    assert record["investigation_id"] == "inv-1"
    assert record["resolved_query"]["node_ids"] == ["a", "b"]  # type: ignore[index]
    assert record["result_cardinality"] == 2


def test_a_branch_of_a_case_in_another_unit_answers_not_found(client: TestClient) -> None:
    _as(OTHER_UNIT)
    response = client.post("/v1/investigations/inv-1/branch", json={"node_ids": ["a"]})

    assert response.status_code == 404
    assert client.investigations.created == []  # type: ignore[attr-defined]


# --- the open or hidden flag of a tab ---------------------------------------------------------


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
    branch = client.post("/v1/investigations/inv-1/branch", json={"node_ids": ["a"]}).json()

    assert (
        client.put(f"/v1/investigations/{branch['id']}/tab", json={"hidden": True}).status_code
        == 204
    )
    assert _listing(client)[branch["id"]]["tab_hidden"] is True

    _as(BOB)
    assert _listing(client)[branch["id"]]["tab_hidden"] is False


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
