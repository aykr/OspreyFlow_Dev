"""The one alert queue's routes, and a hotlist's audience (`spec/06_DECISIONS.md` ADR-133 stage (a)
and ruling 3). `CLAUDE.md` rule 4: every read path has its access-control test — refused without
sign-in, refused without the right, and kept to the case (a person with no level in the case is told
it does not exist; a Viewer reads, an Editor triages).

The app runs with its lifespan replaced, so nothing outside the test is started: the alert and
hotlist stores are the real Postgres ones (connected inside the app's own event loop), the graph a
fake that answers as the adapter does (a hidden id is simply absent), the case store the level-aware
one `test_investigation_levels.py` uses, and the deployment's monitoring settings are set per test.
Real Postgres (`make dev-up`, or a throwaway one).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.api.alerts import AlertStore
from services.api.app import (
    app,
    get_alerts_store,
    get_analytics,
    get_audit,
    get_graph,
    get_hotlists_store,
    get_investigations,
    get_monitoring_settings,
    get_principal,
    get_principal_names,
)
from services.api.config import MonitoringSettings, PostgresConfig
from services.api.hotlists import HotlistStore
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)

from conduit_common.identity import new_id
from schemas.domain import (
    Alert,
    AlertMode,
    AuditStub,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


class _Case:
    """Holds a level per account on one case, applied as the real store applies it, and the case's
    grants for the assignee list."""

    def __init__(self, case_id: str, levels: dict[str, AccessLevel]) -> None:
        self.case_id = case_id
        self.levels = levels

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        held = self.levels.get(principal.id)
        if investigation_id != self.case_id or held is None:
            raise InvestigationNotFoundError(investigation_id)
        if held.rank < need.rank:
            raise InsufficientAccessError(f"{need.value} needed")
        return Investigation(id=investigation_id, name="A case", created_at=NOW,
                             created_by="author", owning_unit="unit-a")  # fmt: skip

    async def list_grants(self, investigation_id: str) -> dict[str, AccessLevel]:
        return dict(self.levels) if investigation_id == self.case_id else {}


class _Graph:
    def __init__(self, hidden: set[str]) -> None:
        self.hidden = hidden

    def _node(self, node_id: str) -> Node:
        return Node(
            id=node_id, type="Person", properties={"name": f"Person {node_id}"},
            provenance=Provenance(state=ProvenanceState.ASSERTED, first_seen=NOW, sources=[
                SourceRef(document_id="doc-1", locator="row 1", excerpt_hash="a" * 64)]),
            handling={"classification": "OFFICIAL", "handling_code": "P",  # type: ignore[arg-type]
                      "originator": "unit-a", "owning_unit": "unit-a"},
            audit=AuditStub(created_at=NOW, created_by="loader-1"),
        )  # fmt: skip

    async def get_nodes(self, node_ids: Any, principal: Principal) -> list[Node]:
        return [self._node(i) for i in sorted(set(node_ids)) if i not in self.hidden]

    async def get_node(self, node_id: str, principal: Principal, **_: object) -> Node | None:
        return None if node_id in self.hidden else self._node(node_id)

    async def edges_among(self, node_ids: Any, principal: Principal) -> list[Any]:
        return []


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _Names:
    """The identity provider as the directory reads it, refusals included (rule 15): an id that is
    no account (a seed's own principal, such as `ledger-seed-worker`) is a 404, and a service
    account (a dashboard's) is an account but no person."""

    SERVICE = "service-account-osprey-dashboard-1"

    def __init__(self, unknown: frozenset[str] = frozenset({"ledger-seed-worker"})) -> None:
        self.unknown = unknown

    async def display_names(self, ids: Any) -> dict[str, str]:
        return {i: f"Name of {i}" for i in ids if i not in self.unknown}

    async def people(self, ids: Any) -> set[str]:
        return {i for i in ids if i not in self.unknown and i != self.SERVICE}


@asynccontextmanager
async def _no_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


class _World:
    def __init__(self) -> None:
        unit = f"unit-{new_id()}"
        self.unit = unit
        self.case = f"case-{new_id()}"
        self.owner = Principal(id=f"owner-{new_id()}", clearance="OFFICIAL", org_unit=unit,
                               roles=["analyst"], datasets=["ds-1"])  # fmt: skip
        self.member = self.owner.model_copy(update={"id": f"member-{new_id()}"})
        self.viewer = self.owner.model_copy(update={"id": f"viewer-{new_id()}"})
        self.outsider = self.owner.model_copy(update={"id": f"outsider-{new_id()}"})
        self.no_right = self.owner.model_copy(update={"id": f"noright-{new_id()}", "roles": []})
        self.as_: Principal = self.owner
        self.investigations = _Case(self.case, {
            self.owner.id: AccessLevel.AUTHOR, self.member.id: AccessLevel.EDITOR,
            self.viewer.id: AccessLevel.VIEWER, self.no_right.id: AccessLevel.EDITOR,
        })  # fmt: skip
        self.settings = MonitoringSettings("only_me", hotlist_audience_editable=True)
        self.graph = _Graph(hidden={"n-hidden"})
        self.audit = _Audit()
        self.alerts: AlertStore | None = None
        self.hotlists: HotlistStore | None = None

    async def alerts_store(self) -> AlertStore:
        if self.alerts is None:
            self.hotlists = await self.hotlists_store()
            self.alerts = await AlertStore.connect(PostgresConfig.from_env().dsn)
        return self.alerts

    async def hotlists_store(self) -> HotlistStore:
        if self.hotlists is None:
            self.hotlists = await HotlistStore.connect(PostgresConfig.from_env().dsn)
        return self.hotlists


@pytest.fixture
def world() -> Iterator[tuple[_World, TestClient]]:
    w = _World()
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.dependency_overrides.update({
        get_principal: lambda: w.as_,
        get_investigations: lambda: w.investigations,
        get_graph: lambda: w.graph,
        get_analytics: lambda: None,  # no alert here cites a transaction
        get_audit: lambda: w.audit,
        get_alerts_store: w.alerts_store,
        get_hotlists_store: w.hotlists_store,
        get_monitoring_settings: lambda: w.settings,
        get_principal_names: lambda: _Names(),
    })  # fmt: skip
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield w, client
            client.portal.call(_close, w)  # type: ignore[union-attr]
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous


async def _close(w: _World) -> None:
    for store in (w.alerts, w.hotlists):
        if store is not None:
            await store.close()


def _save(client: TestClient, w: _World, alert: Alert) -> None:
    async def save() -> None:
        await (await w.alerts_store()).save(alert)

    client.portal.call(save)  # type: ignore[union-attr]


def _alert(w: _World, rule_id: str, **fields: object) -> Alert:
    values: dict[str, Any] = {"id": new_id(), "rule_id": rule_id, "owner_id": w.owner.id,
                              "mode": AlertMode.FULL, "referent_node_ids": ["n-1"],
                              "created_at": NOW, "dataset_id": "ds-1"}  # fmt: skip
    values.update(fields)
    return Alert(**values)


def _hotlist(client: TestClient, w: _World, audience: str) -> str:
    w.as_ = w.owner
    made = client.post(f"/v1/investigations/{w.case}/hotlists",
                       json={"identifier": "07700 900310", "review_date": "2027-01-01",
                             "audience": audience})  # fmt: skip
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


Q = "/v1/investigations/{case}/alert-queue"


# --- the queue: sign-in, the right, the case ---------------------------------------------------


def test_the_queue_is_refused_without_sign_in(world: tuple[_World, TestClient]) -> None:
    w, client = world
    del app.dependency_overrides[get_principal]
    for method, path in (
        ("GET", Q), ("GET", Q + "/a-1"), ("POST", Q + "/a-1/assign"),
        ("GET", "/v1/investigations/{case}/alert-assignees"),
        ("PUT", "/v1/investigations/{case}/hotlists/h-1/audience"),
    ):  # fmt: skip
        response = client.request(method, path.format(case=w.case), json={})
        assert response.status_code in (401, 403), (path, response.status_code)
        assert "authenticated" in response.text.lower(), response.text


def test_the_queue_is_refused_without_the_right(world: tuple[_World, TestClient]) -> None:
    w, client = world
    w.as_ = w.no_right
    for method, path in (
        ("GET", Q), ("GET", Q + "/a-1"), ("POST", Q + "/a-1/assign"),
        ("GET", "/v1/investigations/{case}/alert-assignees"),
        ("PUT", "/v1/investigations/{case}/hotlists/h-1/audience"),
    ):  # fmt: skip
        response = client.request(method, path.format(case=w.case), json={"assignee": "x",
                                                                          "audience": "team"})
        assert response.status_code == 403, (path, response.text)
        assert response.json()["detail"]["error"] == "right_required"


def test_the_queue_is_the_cases_and_triage_needs_an_editor(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    alert = _alert(w, "typology:r1", investigation_id=w.case, typology="structuring",
                   words="4 movements")  # fmt: skip
    _save(client, w, alert)
    base = Q.format(case=w.case)

    w.as_ = w.outsider
    assert client.get(base).status_code == 404
    assert client.get(f"{base}/{alert.id}").status_code == 404
    assert client.get(f"/v1/investigations/{w.case}/alert-assignees").status_code == 404

    w.as_ = w.viewer
    listed = client.get(base)
    assert listed.status_code == 200 and [r["alert"]["id"] for r in listed.json()] == [alert.id]
    assert listed.json()[0]["kind"] == "typology" and listed.json()[0]["severity"] == "medium"
    assert client.get(f"{base}/{alert.id}").status_code == 200
    given_by_viewer = client.post(f"{base}/{alert.id}/assign", json={"assignee": w.member.id})
    assert given_by_viewer.status_code == 403
    assert client.get(f"/v1/investigations/{w.case}/alert-assignees").status_code == 403

    w.as_ = w.owner
    names = client.get(f"/v1/investigations/{w.case}/alert-assignees")
    assert names.status_code == 200
    assert {a["id"] for a in names.json()} == {w.owner.id, w.member.id, w.no_right.id}
    given = client.post(f"{base}/{alert.id}/assign", json={"assignee": w.member.id})
    assert given.status_code == 200 and given.json()["assignee"] == w.member.id
    refused = client.post(f"{base}/{alert.id}/assign", json={"assignee": w.viewer.id})
    assert refused.status_code == 422 and "not a member" in refused.json()["detail"]
    assert [r["action"] for r in w.audit.records][-1] == "alert_assigned"


def test_an_alert_is_never_given_to_a_service_account(world: tuple[_World, TestClient]) -> None:
    """Build order step 15: *Give to* in the Ledger case offered `ledger-seed-worker`, the seed's own
    principal, which holds the case's Author grant because it made the case. Service accounts are not
    people: the list is the case's Editors and Authors the identity provider knows as people, and
    giving an alert to anyone else is refused."""
    w, client = world
    seeder, dashboard = "ledger-seed-worker", _Names.SERVICE
    w.investigations.levels.update({seeder: AccessLevel.AUTHOR, dashboard: AccessLevel.EDITOR})
    alert = _alert(w, "typology:r1", investigation_id=w.case, typology="structuring",
                   words="4 movements")  # fmt: skip
    _save(client, w, alert)
    w.as_ = w.owner
    offered = client.get(f"/v1/investigations/{w.case}/alert-assignees")
    assert offered.status_code == 200
    assert {a["id"] for a in offered.json()} == {w.owner.id, w.member.id, w.no_right.id}
    for account in (seeder, dashboard):
        given = f"{Q.format(case=w.case)}/{alert.id}/assign"
        refused = client.post(given, json={"assignee": account})
        assert refused.status_code == 422, account


def test_the_queue_shows_every_kind_filters_them_and_withholds_a_hidden_one(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    hotlist_id = _hotlist(client, w, "team")
    typology = _alert(w, "typology:r1", investigation_id=w.case, typology="kyc_screening")
    hotlist = _alert(w, f"hotlist:{hotlist_id}", team=w.unit)
    monitor = _alert(w, f"monitor:{new_id()}", team=w.unit)
    hidden = _alert(w, f"monitor:{new_id()}", team=w.unit, referent_node_ids=["n-hidden"])
    for alert in (typology, hotlist, monitor, hidden):
        _save(client, w, alert)
    base = Q.format(case=w.case)

    w.as_ = w.member  # a team member, not the owner
    rows = client.get(base).json()
    assert w.audit.records[-1]["result_cardinality"] == 3  # the hidden one is not counted
    assert {r["kind"] for r in rows} == {"typology", "hotlist", "monitor"}
    assert hidden.id not in [r["alert"]["id"] for r in rows]
    assert client.get(f"{base}/{hidden.id}").status_code == 404
    assert [r["alert"]["id"] for r in client.get(f"{base}?kind=hotlist").json()] == [hotlist.id]
    assert {r["alert"]["id"] for r in client.get(f"{base}?severity=high").json()} == {
        typology.id, hotlist.id,
    }  # fmt: skip
    explained = client.get(f"{base}/{monitor.id}").json()
    assert explained["kind"] == "monitor" and explained["audience"] == "team"


def test_closing_without_a_reason_is_refused(world: tuple[_World, TestClient]) -> None:
    w, client = world
    alert = _alert(w, f"monitor:{new_id()}", team=w.unit)
    _save(client, w, alert)
    path = f"{Q.format(case=w.case)}/{alert.id}/disposition"
    w.as_ = w.member
    for reason in ("", "   "):
        refused = client.post(path, json={"disposition": "false_positive", "reason": reason})
        assert refused.status_code == 422, refused.text
    closed = client.post(path, json={"disposition": "false_positive", "reason": "known number"})
    assert closed.status_code == 200 and closed.json()["status"] == "closed"


# The owner's answer of 1 November 2026 (ADR-133 decision 7's closed list, named): the five closing
# reasons, each a value the route takes, with its label as the Glass says it.
CLOSING_REASONS = {
    "true_positive": "True match",
    "false_positive": "False positive",
    "duplicate": "Duplicate",
    "no_further_action": "No further action",
    "referred": "Referred",
}


@pytest.mark.parametrize("reason", sorted(CLOSING_REASONS))
def test_each_of_the_five_closing_reasons_closes_an_alert(
    world: tuple[_World, TestClient], reason: str
) -> None:
    w, client = world
    alert = _alert(w, f"monitor:{new_id()}", team=w.unit)
    _save(client, w, alert)
    w.as_ = w.member
    closed = client.post(f"{Q.format(case=w.case)}/{alert.id}/disposition",
                         json={"disposition": reason, "reason": "seen on the file"})  # fmt: skip
    assert closed.status_code == 200, closed.text
    assert (closed.json()["status"], closed.json()["disposition"]) == ("closed", reason)


def test_a_reason_outside_the_closed_list_is_refused_in_words(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    alert = _alert(w, f"monitor:{new_id()}", team=w.unit)
    _save(client, w, alert)
    w.as_ = w.member
    path = f"{Q.format(case=w.case)}/{alert.id}/disposition"
    for other in ("escalated", "True match", "TRUE_POSITIVE", ""):
        refused = client.post(path, json={"disposition": other, "reason": "seen on the file"})
        assert refused.status_code == 422, (other, refused.text)
        said = refused.text
        assert ("the closing reason must be one of: True match, False positive, Duplicate, "
                "No further action, Referred") in said, (other, said)  # fmt: skip
    still = client.get(f"{Q.format(case=w.case)}/{alert.id}").json()
    assert still["alert"]["status"] != "closed", "a refused reason closes nothing"


# --- the hotlist's audience (ruling 3) -----------------------------------------------------------


def test_a_new_hotlist_takes_the_deployment_default_and_no_existing_one_changes(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    w.as_ = w.owner
    path = f"/v1/investigations/{w.case}/hotlists"
    before = client.post(path, json={"identifier": "07700 900311", "review_date": "2027-01-01"})
    assert before.json()["audience"] == "only_me"

    w.settings = MonitoringSettings(hotlist_audience="team", hotlist_audience_editable=True)
    after = client.post(path, json={"identifier": "07700 900312", "review_date": "2027-01-01"})
    assert after.json()["audience"] == "team"
    listed = client.get(path).json()
    audiences = {h["id"]: h["audience"] for h in listed["hotlists"]}
    assert audiences[before.json()["id"]] == "only_me", "an existing hotlist keeps its audience"
    assert listed["audience_default"] == "team" and listed["audience_editable"] is True


def test_with_editing_off_the_choice_is_refused_in_words(world: tuple[_World, TestClient]) -> None:
    w, client = world
    hotlist_id = _hotlist(client, w, "only_me")
    w.settings = MonitoringSettings(hotlist_audience="only_me", hotlist_audience_editable=False)
    path = f"/v1/investigations/{w.case}/hotlists"

    changed = client.put(f"{path}/{hotlist_id}/audience", json={"audience": "team"})
    assert changed.status_code == 403
    assert changed.json()["error"] == "hotlist_audience_fixed"
    assert "cannot be changed" in changed.json()["detail"]
    made = client.post(path, json={"identifier": "07700 900313", "review_date": "2027-01-01",
                                   "audience": "team"})  # fmt: skip
    assert made.status_code == 403 and "cannot be changed" in made.json()["detail"]
    # The deployment's own value is not a choice, and is accepted.
    same = client.post(path, json={"identifier": "07700 900314", "review_date": "2027-01-01",
                                   "audience": "only_me"})  # fmt: skip
    assert same.status_code == 201


def test_the_owner_alone_changes_a_hotlists_audience(world: tuple[_World, TestClient]) -> None:
    w, client = world
    hotlist_id = _hotlist(client, w, "only_me")
    path = f"/v1/investigations/{w.case}/hotlists/{hotlist_id}/audience"

    w.as_ = w.member
    assert client.put(path, json={"audience": "team"}).status_code == 404
    w.as_ = w.viewer
    assert client.put(path, json={"audience": "team"}).status_code == 403
    w.as_ = w.outsider
    assert client.put(path, json={"audience": "team"}).status_code == 404
    w.as_ = w.owner
    changed = client.put(path, json={"audience": "team"})
    assert changed.status_code == 200 and changed.json()["audience"] == "team"
    assert w.audit.records[-1]["action"] == "hotlist_audience_changed"
