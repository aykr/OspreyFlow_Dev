"""The Lists screen's routes (`spec/06_DECISIONS.md` ADR-133 decision 4, stage (c)). `CLAUDE.md` rule 4:
every read path has its access-control test — refused without sign-in, refused without the right —
and rule 7: a reader of the alert queue sees each list, never the deployment-wide counts of customers
re-screened and alerts raised that only whoever may load lists is shown.

The app runs with its lifespan replaced; the screening store is the real Postgres one (a throwaway
server), the rules and the graph stand-ins that hold nothing (re-screening itself is
`test_screening_refresh.py`'s), and the ingest folder a temporary one holding the synthetic list.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_alerts_store,
    get_audit,
    get_datasets,
    get_graph,
    get_handling_scheme,
    get_principal,
    get_principal_resolver,
    get_screening_lists,
    get_typology_rules,
    get_valkey,
)
from services.api.config import PostgresConfig
from services.api.screening import ScreeningListStore
from services.api.screening_refresh import SYNTHETIC_MANIFEST

from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal

from .corpus_counts import field_names_reachable

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-a", roles=["analyst"])
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-a", roles=["osprey-admin"])
ENGINEER = Principal(id="engineer-1", clearance="OFFICIAL", org_unit="unit-a", roles=["data_engineer"])
NOBODY = Principal(id="nobody-1", clearance="OFFICIAL", org_unit="unit-a", roles=[])
LIST = {"list_name": "Synthetic list", "source": "opensanctions",
        "location": "lists/synthetic_opensanctions_v1.ftm.json"}  # fmt: skip
MANAGE = [("GET", "/v1/admin/screening-lists"), ("POST", "/v1/admin/screening-lists"),
          ("POST", "/v1/admin/screening-lists/Synthetic list/refresh")]  # fmt: skip


@asynccontextmanager
async def _no_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _Nothing:
    async def list_active_of_typology(self, typology: str) -> list[Any]:
        return []


class _Resolver:
    async def resolve_for_owner(self, owner_id: str) -> Principal | None:
        return None


class _World:
    def __init__(self) -> None:
        self.as_ = ADMIN
        self.audit = _Audit()
        self.store: ScreeningListStore | None = None

    async def screening(self) -> ScreeningListStore:
        if self.store is None:
            dsn = PostgresConfig.from_env().dsn
            # The store first, so its tables exist on a fresh server before they are emptied.
            self.store = await ScreeningListStore.connect(dsn)
            conn = await asyncpg.connect(dsn)
            await conn.execute("DELETE FROM screening_list_updates; DELETE FROM screening_lists; "
                               "DELETE FROM screening_entries WHERE list_name = 'Synthetic list'")  # fmt: skip
            await conn.close()
        return self.store


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[_World, TestClient]]:
    (tmp_path / "lists").mkdir()
    shutil.copy(SYNTHETIC_MANIFEST.parent / "synthetic_opensanctions_v1.ftm.json", tmp_path / "lists")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(tmp_path))
    w = _World()
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.dependency_overrides.update({
        get_principal: lambda: w.as_,
        get_audit: lambda: w.audit,
        get_screening_lists: w.screening,
        get_typology_rules: lambda: _Nothing(),
        get_datasets: lambda: None,
        get_graph: lambda: None,
        get_alerts_store: lambda: None,
        get_valkey: lambda: None,
        get_principal_resolver: lambda: _Resolver(),
        get_handling_scheme: load_uk_le_scheme,
    })  # fmt: skip
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield w, client
            if w.store is not None:
                client.portal.call(w.store.close)  # type: ignore[union-attr]
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous


def test_the_lists_are_refused_without_sign_in(world: tuple[_World, TestClient]) -> None:
    _, client = world
    del app.dependency_overrides[get_principal]
    for method, path in [("GET", "/v1/screening-lists"), *MANAGE]:
        response = client.request(method, path, json=LIST)
        assert response.status_code in (401, 403), (path, response.status_code)
        assert "authenticated" in response.text.lower(), response.text


def test_the_lists_are_refused_without_the_right(world: tuple[_World, TestClient]) -> None:
    w, client = world
    w.as_ = NOBODY
    response = client.get("/v1/screening-lists")
    assert response.status_code == 403 and response.json()["detail"]["right"] == "read_alert_queue"
    for who in (NOBODY, ANALYST):  # an analyst reads the lists; only a loader of lists manages them
        w.as_ = who
        for method, path in MANAGE:
            response = client.request(method, path, json=LIST)
            assert response.status_code == 403, (who.id, path, response.status_code)
            assert response.json()["detail"]["right"] == "load_screening_lists"


def test_a_list_is_subscribed_refreshed_and_shown(world: tuple[_World, TestClient]) -> None:
    w, client = world
    made = client.post("/v1/admin/screening-lists", json=LIST)
    assert made.status_code == 201, made.text
    assert made.json()["licence"].startswith("CC BY-NC 4.0")
    # The owner's answer of 1 November 2026: marked "licence not confirmed", with the reason.
    assert made.json()["licence_confirmed"] is False
    assert "commercial use" in made.json()["licence_note"]
    refreshed = client.post("/v1/admin/screening-lists/Synthetic list/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert (refreshed.json()["outcome"], refreshed.json()["added"]) == ("updated", 10)
    shown = client.get("/v1/admin/screening-lists").json()
    (one,) = shown["lists"]
    assert (one["entries"], one["synthetic"], one["failure"]) == (10, True, None)
    assert one["version"].startswith("sha256:") and shown["can_manage"] is True
    assert shown["updates"][0]["words"].startswith(f"Version {one['version']}: 10 added")
    assert [r["action"] for r in w.audit.records][-3:] == [
        "screening_list_subscribed", "screening_list_refreshed", "list_screening_lists"]
    # A data engineer holds the same right (ADR-112).
    w.as_ = ENGINEER
    assert client.get("/v1/admin/screening-lists").status_code == 200


def test_a_reader_sees_each_list_but_not_the_deployment_wide_counts(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    client.post("/v1/admin/screening-lists", json=LIST)
    client.post("/v1/admin/screening-lists/Synthetic list/refresh")
    w.as_ = ANALYST
    shown = client.get("/v1/screening-lists")
    assert shown.status_code == 200
    body = shown.json()
    assert [x["list_name"] for x in body["lists"]] == ["Synthetic list"]
    assert "updates" not in body and body["can_manage"] is False
    assert "re-screened" not in shown.text and "alert" not in shown.text


def test_the_readers_route_cannot_carry_the_deployment_wide_counts() -> None:
    """Violation caught (rule 7): the reader's route answered with the administrator's model, its
    refreshes held empty by the handler alone, so one line changed there would send every reader
    the counts of customers re-screened and alerts raised across every case. Its own model has no
    field to hold them. Pure: walks the route's response model, opens no connection."""
    (route,) = [
        r for r in app.routes
        if isinstance(r, APIRoute) and r.path == "/v1/screening-lists" and "GET" in r.methods
    ]  # fmt: skip
    reachable = field_names_reachable(route.response_model)
    assert "lists" in reachable, "the walk sees the route's model"
    assert reachable & {"updates", "rescreened", "alerts"} == set()


def test_a_location_outside_the_ingest_folder_is_refused_at_subscription(
    world: tuple[_World, TestClient],
) -> None:
    _, client = world
    response = client.post("/v1/admin/screening-lists", json={**LIST, "location": "../../etc/passwd"})
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == (
        "the list's location is outside the ingest folder; nothing was read")


def test_refreshing_a_list_never_subscribed_says_so(world: tuple[_World, TestClient]) -> None:
    _, client = world
    response = client.post("/v1/admin/screening-lists/No such list/refresh")
    assert response.status_code == 404
    assert response.json()["detail"]["message"] == "no list is subscribed as “No such list”"


# --- the admin's own unit (the owner's answer of 1 November 2026; rules 3, 4 and 7) --------------

UNIT_A = Principal(id="officer-a", clearance="OFFICIAL", org_unit="unit-a", roles=["analyst"])
UNIT_B = Principal(id="officer-b", clearance="OFFICIAL", org_unit="unit-b", roles=["analyst"])
V1 = {**LIST, "location": "lists/synthetic_opensanctions_v1.ftm.json"}
V2 = {**LIST, "location": "lists/synthetic_opensanctions_v2.ftm.json"}


class _TwoCases:
    async def ids_of_case(self, investigation_id: str) -> list[str]:
        return {"case-a": ["ds-a"], "case-b": ["ds-b"]}.get(investigation_id, [])


class _TwoUnits:
    async def resolve_for_owner(self, owner_id: str) -> Principal | None:
        return {UNIT_A.id: UNIT_A, UNIT_B.id: UNIT_B}.get(owner_id)


class _ScreeningRules:
    def __init__(self, rules: list[Any]) -> None:
        self.rules = rules

    async def list_active_of_typology(self, typology: str) -> list[Any]:
        return self.rules if typology == "kyc_screening" else []


def _screening_rule(rule_id: str, case: str, owner: Principal, name: str) -> Any:
    from datetime import UTC, datetime

    from schemas.domain import KycScreeningParams, TypologyRule

    return TypologyRule(id=rule_id, investigation_id=case, owner_id=owner.id, name=name,
                        params=KycScreeningParams(), trigger="post_commit",
                        created_at=datetime(2026, 11, 1, tzinfo=UTC))  # fmt: skip


@pytest.fixture
def two_units(
    world: tuple[_World, TestClient], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[_World, TestClient, Any]:
    """Unit A's case holds one customer the second version lists; unit B's case holds three, two
    of them listed. Each unit's screening rule is deployed by one of its own officers."""
    from services.api.dataset_scope import DatasetStampingGraph

    from .test_screening_refresh import _customer, _Graph, _Queue

    w, client = world
    shutil.copy(SYNTHETIC_MANIFEST.parent / "synthetic_opensanctions_v2.ftm.json", tmp_path / "lists")
    graph = _Graph([
        _customer("a-zelinsky", "Tomas", "Zelinsky", dob="1997-01-30", datasets=("ds-a",)),
        _customer("b-zelinsky", "Tomas", "Zelinsky", dob="1997-01-30", datasets=("ds-b",)),
        _customer("b-hale", "Marcus", "Hale", dob="1981-03-07", datasets=("ds-b",)),
        _customer("b-other", "Someone", "Else", datasets=("ds-b",)),
    ])  # fmt: skip
    queue = _Queue()
    # The refresh route reads each case's datasets from the app's state, as the lifespan sets it.
    monkeypatch.setattr(app.state, "datasets", _TwoCases(), raising=False)
    app.dependency_overrides.update({
        get_graph: lambda: DatasetStampingGraph(graph),  # type: ignore[arg-type]
        get_alerts_store: lambda: queue,
        get_valkey: lambda: queue,
        get_principal_resolver: lambda: _TwoUnits(),
        get_typology_rules: lambda: _ScreeningRules([]),
    })  # fmt: skip
    assert client.post("/v1/admin/screening-lists", json=V1).status_code == 201
    assert client.post("/v1/admin/screening-lists/Synthetic list/refresh").status_code == 200
    rules = [_screening_rule("rule-a", "case-a", UNIT_A, "Unit A screening"),
             _screening_rule("rule-b", "case-b", UNIT_B, "Unit B screening")]  # fmt: skip
    app.dependency_overrides[get_typology_rules] = lambda: _ScreeningRules(rules)
    assert client.post("/v1/admin/screening-lists", json=V2).status_code == 201
    return w, client, queue


def test_a_refresh_counts_only_the_admins_own_unit(
    two_units: tuple[_World, TestClient, Any],
) -> None:
    """Violation caught: the refresh answered with the counts of every case in the deployment —
    unit B's three customers and its alert told to unit A's administrator (rule 7)."""
    _, client, queue = two_units
    refreshed = client.post("/v1/admin/screening-lists/Synthetic list/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert len(queue.alerts) == 2, "both units' rules ran: the deployment re-screened four customers"
    body = refreshed.json()
    assert (body["rescreened"], body["alerts"]) == (1, 1), body
    assert "1 customer re-screened" in body["words"] and "1 alert raised" in body["words"], body
    assert "Unit B" not in refreshed.text and "4 customers" not in refreshed.text


def test_a_second_units_rescreening_is_invisible_in_the_admin_list(
    two_units: tuple[_World, TestClient, Any],
) -> None:
    """Rule 4's access-control test for `GET /v1/admin/screening-lists`: an administrator of unit
    B reads only unit B's counts, unit A's only unit A's, and one of a unit with no screening rule
    reads none — not even a zero that differs from another unit's."""
    w, client, _ = two_units
    client.post("/v1/admin/screening-lists/Synthetic list/refresh")
    seen: dict[str, tuple[int, int, str]] = {}
    for unit in ("unit-a", "unit-b", "unit-c"):
        w.as_ = ADMIN.model_copy(update={"id": f"admin-{unit}", "org_unit": unit})
        latest = client.get("/v1/admin/screening-lists").json()["updates"][0]
        seen[unit] = (latest["rescreened"], latest["alerts"], latest["words"])
    assert seen["unit-a"][:2] == (1, 1) and seen["unit-b"][:2] == (3, 1)
    assert seen["unit-c"][:2] == (0, 0)
    assert "0 customers re-screened" in seen["unit-c"][2] and "0 alerts raised" in seen["unit-c"][2]
    assert "Unit B" not in seen["unit-a"][2] and "Unit A" not in seen["unit-b"][2]
    for unit, (_, _, words) in seen.items():
        assert "4 customers" not in words and "2 alerts" not in words, (unit, words)


def test_each_list_says_whether_its_licence_is_confirmed(world: tuple[_World, TestClient]) -> None:
    """The owner's answer of 1 November 2026 (ADR-133 Amendment 3): UN and OpenSanctions are marked
    "licence not confirmed" with the reason in words, on the reader's route as on the manager's;
    the other connectors carry no such mark."""
    w, client = world
    for name, source in (("Synthetic list", "opensanctions"), ("Synthetic list UN", "un_consolidated"),
                         ("Synthetic list OFAC", "ofac_sdn")):  # fmt: skip
        made = client.post("/v1/admin/screening-lists",
                           json={"list_name": name, "source": source, "location": "lists/x"})  # fmt: skip
        assert made.status_code == 201, made.text
    w.as_ = ANALYST
    shown = {x["source"]: x for x in client.get("/v1/screening-lists").json()["lists"]}
    assert shown["un_consolidated"]["licence_confirmed"] is False
    assert "non-commercial use only" in shown["un_consolidated"]["licence_note"]
    assert shown["opensanctions"]["licence_confirmed"] is False
    assert shown["ofac_sdn"]["licence_confirmed"] is True and shown["ofac_sdn"]["licence_note"] is None


def test_the_closed_ofsi_list_says_so_and_its_successor_does_not(
    world: tuple[_World, TestClient],
) -> None:
    """ADR-133 Amendment 6: the OFSI connector reads a list closed on 28 January 2026, and says so in
    words on the Lists tab; the UK Sanctions List (FCDO), its successor, is a list of its own whose
    licence is confirmed and which is not closed."""
    w, client = world
    for name, source in (("Synthetic list OFSI", "ofsi_consolidated"),
                         ("Synthetic list UKSL", "uk_sanctions_list")):  # fmt: skip
        made = client.post("/v1/admin/screening-lists",
                           json={"list_name": name, "source": source, "location": "lists/x"})  # fmt: skip
        assert made.status_code == 201, made.text
    w.as_ = ANALYST
    shown = {x["source"]: x for x in client.get("/v1/screening-lists").json()["lists"]}
    assert "closed on 28 January 2026" in shown["ofsi_consolidated"]["closed_note"]
    assert "UK Sanctions List" in shown["ofsi_consolidated"]["closed_note"]
    successor = shown["uk_sanctions_list"]
    assert successor["closed_note"] is None and successor["licence_confirmed"] is True
    assert successor["licence"].startswith("Open Government Licence v3.0")


def test_the_glass_says_the_same_closed_list_words_as_the_conduit() -> None:
    """The subscribe form says the OFSI list is closed before any list exists, so the Glass holds the
    words too (`ListsPanel.tsx`'s `CLOSED_LISTS`). Pure: a drift check, opening no connection."""
    from services.api.screening_refresh import CLOSED_LISTS
    from tools.layout import CORE

    panel = (CORE / "apps" / "workspace" / "src" / "alerts" / "ListsPanel.tsx").read_text(encoding="utf-8")
    block = panel[panel.index("export const CLOSED_LISTS"):]
    block = block[: block.index("};")]
    assert sorted(CLOSED_LISTS) == ["ofsi_consolidated"]
    for source, words in CLOSED_LISTS.items():
        assert f'{source}:\n    "{words}",' in block, source


def test_the_glass_says_the_same_licence_reasons_as_the_conduit() -> None:
    """The subscribe form says why a connector's licence is not confirmed before any list exists, so
    the Glass holds the reasons too (`ListsPanel.tsx`'s `LICENCE_NOT_CONFIRMED`). Pure: a drift
    check between the two, opening no connection."""
    from services.api.screening_refresh import LICENCE_NOT_CONFIRMED
    from tools.layout import CORE

    panel = (CORE / "apps" / "workspace" / "src" / "alerts" / "ListsPanel.tsx").read_text(encoding="utf-8")
    block = panel[panel.index("export const LICENCE_NOT_CONFIRMED"):]
    block = block[: block.index("};")]
    assert sorted(LICENCE_NOT_CONFIRMED) == ["opensanctions", "un_consolidated"]
    for source, reason in LICENCE_NOT_CONFIRMED.items():
        assert f'{source}:\n    "{reason}",' in block, source
