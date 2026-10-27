"""`POST /v1/investigations/{id}/working-set/add-by-identifiers` (ADR-128 decision 1, B2): the
route's half. The count and the add are `add_by_identifiers.py`'s and the working set's, proved in
`test_add_by_identifiers.py` and `test_add_by_identifiers_service.py`; the real adapter's filter is
`test_add_by_identifiers_live.py`. As `test_explore_routes.py` does, `get_principal` is the real one
with a stand-in token resolver, so the graph is asked with the principal this case builds, carrying
exactly the case's datasets (rule 4, and `CLAUDE.md` rule 12's fake-that-hides-the-access-control).

What a mistake would do, and the case that catches it:

- a list naming someone the analyst may not see answered, audited or acted on differently from one
  naming a made-up person, which tells the analyst the person exists (rule 3)
  (`test_a_list_naming_a_hidden_person_is_answered_as_one_naming_a_made_up_one`);
- the count-only request adding (`test_a_count_adds_nothing_and_confirm_adds`);
- an identifier written into the audit entry
  (`test_the_audit_entry_holds_counts_and_never_an_identifier`);
- 5,001 truncated, or refused without saying the limit
  (`test_more_than_5000_is_refused_by_name_and_nothing_is_looked_up`);
- a list past the cap added in part, or refused without the three options
  (`test_a_list_past_the_cap_gets_the_typed_limit_with_its_three_options`);
- the graph asked as someone other than the case's reader
  (`test_the_graph_is_asked_with_the_cases_datasets`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_graph,
    get_history,
    get_investigations,
    get_valkey,
    get_working_set,
)
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.working_set.models import (
    DeltaAdd,
    ExpansionOutcome,
    LimitExceeded,
    LimitExceededError,
)

from schemas.domain import Edge, Node, Principal
from tests.services.api.any_case import AnyCase
from tests.services.api.test_add_by_identifiers import _endpoint, _person
from tests.services.api.test_search_route import _FakeAudit

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
PATH = "/v1/investigations/case-e/working-set/add-by-identifiers"


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return ANALYST


class _Graph:
    def __init__(self) -> None:
        self.visible = {
            ("Person", "prison_number", "Z1234ZZ"): _person("p1", prison_number="Z1234ZZ"),
            ("Endpoint", "value_normalised", "+447700900123"):
                _endpoint("e1", "+447700900123", "msisdn"),
        }
        self.calls: list[tuple[str, str, str, Principal]] = []

    async def find_node(
        self,
        entity_type: str,
        identifier_field: str,
        value: str,
        principal: Principal,
        *,
        also: dict[str, str] | None = None,
    ) -> Node | None:
        self.calls.append((entity_type, identifier_field, value, principal))
        return self.visible.get((entity_type, identifier_field, value))


class _WorkingSet:
    def __init__(self) -> None:
        self.adds: list[tuple[str, list[str], bool]] = []
        self.refuse: LimitExceededError | None = None

    async def add_by_identifiers(
        self,
        investigation_id: str,
        nodes: list[Node],
        principal: Principal,
        *,
        with_links: bool = False,
    ) -> ExpansionOutcome:
        if self.refuse is not None:
            raise self.refuse
        self.adds.append((investigation_id, [n.id for n in nodes], with_links))
        edges: list[Edge] = []
        return ExpansionOutcome(delta=DeltaAdd(seq=3, nodes=nodes, edges=edges))

    async def current_membership(self, investigation_id: str) -> tuple[list[Node], list[Edge]]:
        return [], []


class _History:
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    async def record_step(self, investigation_id: str, **kwargs: Any) -> object:
        self.steps.append(kwargs)
        return object()


class _Valkey:
    def __init__(self) -> None:
        self.published = 0

    async def publish(self, channel: str, message: str) -> int:
        self.published += 1
        return 1


class Rig:
    def __init__(self, http: TestClient) -> None:
        self.http = http
        self.graph = _Graph()
        self.working_set = _WorkingSet()
        self.audit = _FakeAudit()
        self.history = _History()
        self.valkey = _Valkey()
        app.dependency_overrides[get_graph] = lambda: self.graph
        app.dependency_overrides[get_working_set] = lambda: self.working_set
        app.dependency_overrides[get_audit] = lambda: self.audit
        app.dependency_overrides[get_history] = lambda: self.history
        app.dependency_overrides[get_valkey] = lambda: self.valkey
        app.dependency_overrides[get_investigations] = AnyCase

    def post(self, identifiers: list[str], **extra: Any) -> Any:
        return self.http.post(PATH, json={"identifiers": identifiers, **extra})


@pytest.fixture
def rig() -> Any:
    store = InMemoryDatasetStore()
    store.add(
        Dataset(
            id="enron",
            name="Enron",
            owning_unit="unit-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="seed",
        )
    )
    store.cases["case-e"] = ["enron"]
    saved = {k: getattr(app.state, k, None) for k in ("principal_resolver", "datasets")}
    app.state.principal_resolver = _Resolver()
    app.state.datasets = store
    yield Rig(TestClient(app, headers={"Authorization": "Bearer token"}))
    app.dependency_overrides.clear()
    for key, value in saved.items():
        setattr(app.state, key, value)


def test_a_count_adds_nothing_and_confirm_adds(rig: Rig) -> None:
    typed = ["Z1234ZZ, 07700 900123\nZ9999ZZ z1234zz"]
    counted = rig.post(typed)
    assert counted.status_code == 200
    assert counted.json() == {
        "counts": {"read": 4, "found": 3, "matched_nothing": 1, "repeated": 1},
        "added": None,
    }
    assert rig.working_set.adds == [] and rig.valkey.published == 0 and rig.history.steps == []
    added = rig.post(typed, confirm=True)
    assert added.status_code == 200
    assert added.json()["counts"] == counted.json()["counts"]
    assert [n["id"] for n in added.json()["added"]["delta"]["nodes"]] == ["p1", "e1"]
    assert rig.working_set.adds == [("case-e", ["p1", "e1"], False)]
    assert rig.valkey.published == 1 and len(rig.history.steps) == 1


def test_the_default_adds_no_links_and_the_option_asks_for_them(rig: Rig) -> None:
    rig.post(["Z1234ZZ"], confirm=True)
    rig.post(["Z1234ZZ"], confirm=True, with_links=True)
    assert [with_links for *_, with_links in rig.working_set.adds] == [False, True]


def test_a_count_does_not_ask_for_links_either(rig: Rig) -> None:
    rig.post(["Z1234ZZ"], with_links=True)
    assert rig.working_set.adds == []


def test_the_graph_is_asked_with_the_cases_datasets(rig: Rig) -> None:
    rig.post(["Z1234ZZ"])
    assert [call[3].datasets for call in rig.graph.calls] == [["enron"]]


def test_a_list_naming_a_hidden_person_is_answered_as_one_naming_a_made_up_one(rig: Rig) -> None:
    """`Z5555ZZ` is held above the analyst's clearance (the graph answers `None`, as the adapter
    does); `Z6666ZZ` is held by nobody. Same body, same audit entry, same lookups, for the count
    and for the add."""
    answers = {}
    for who in ("Z5555ZZ", "Z6666ZZ"):
        rig.audit.records.clear()
        rig.graph.calls.clear()
        rig.working_set.adds.clear()
        counted = rig.post(["Z1234ZZ", who])
        added = rig.post(["Z1234ZZ", who], confirm=True)
        answers[who] = (
            counted.status_code, counted.text, added.status_code, added.text,
            rig.audit.records, len(rig.graph.calls), rig.working_set.adds,
        )  # fmt: skip
    assert answers["Z5555ZZ"] == answers["Z6666ZZ"]
    assert "Z5555ZZ" not in answers["Z5555ZZ"][1] + answers["Z5555ZZ"][3]
    assert '"matched_nothing":1' in answers["Z5555ZZ"][1].replace(" ", "")


def test_the_audit_entry_holds_counts_and_never_an_identifier(rig: Rig) -> None:
    rig.post(["Z1234ZZ, 07700 900123, Z9999ZZ"], confirm=True, with_links=True)
    entry = rig.audit.records[-1]
    assert entry["action"] == "add_by_identifiers"
    assert entry["investigation_id"] == "case-e"
    assert entry["resolved_query"] == {
        "read": 3, "found": 2, "matched_nothing": 1, "repeated": 0,
        "confirm": True, "with_links": True,
    }  # fmt: skip
    assert entry["result_cardinality"] == 2
    text = repr(entry)
    for typed in ("Z1234ZZ", "07700", "900640", "Z9999ZZ", "447700900123"):
        assert typed not in text


def test_more_than_5000_is_refused_by_name_and_nothing_is_looked_up(rig: Rig) -> None:
    lines = [f"Z{n:04d}ZZ" for n in range(5_001)]
    for confirm in (False, True):
        response = rig.post(["\n".join(lines)], confirm=confirm)
        assert response.status_code == 413
        body = response.json()
        assert body["error"] == "too_many_identifiers"
        assert body["cap"] == 5_000 and body["received"] == 5_001
        assert "5,000" in body["message"]
    assert rig.graph.calls == [] and rig.working_set.adds == []
    assert rig.audit.records[-1]["resolved_query"] == {
        "read": 5_001, "refused": True, "cap": 5_000, "confirm": True, "with_links": False,
    }  # fmt: skip


def test_exactly_5000_is_read(rig: Rig) -> None:
    lines = [f"Z{n:04d}ZZ" for n in range(5_000)]
    response = rig.post(["\n".join(lines)])
    assert response.status_code == 200
    assert response.json()["counts"]["read"] == 5_000


def test_a_list_past_the_cap_gets_the_typed_limit_with_its_three_options(rig: Rig) -> None:
    rig.working_set.refuse = LimitExceededError(
        LimitExceeded(cap_kind="nodes", cap=50_000, would_be=50_002)
    )
    response = rig.post(["Z1234ZZ"], confirm=True)
    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "limit_exceeded"
    assert (body["cap_kind"], body["cap"], body["would_be"]) == ("nodes", 50_000, 50_002)
    assert body["options"] == ["branch", "filter", "promote_to_batch"]
    assert rig.valkey.published == 0 and rig.history.steps == []


def test_an_empty_list_is_read_as_nothing(rig: Rig) -> None:
    response = rig.post(["", " \n , "])
    assert response.status_code == 200
    assert response.json()["counts"] == {
        "read": 0, "found": 0, "matched_nothing": 0, "repeated": 0
    }


def test_the_route_answers_no_one_without_a_principal(rig: Rig) -> None:
    anonymous = TestClient(app)
    response = anonymous.post(PATH, json={"identifiers": ["Z1234ZZ"]})
    assert response.status_code in (401, 403)
    assert rig.graph.calls == []
