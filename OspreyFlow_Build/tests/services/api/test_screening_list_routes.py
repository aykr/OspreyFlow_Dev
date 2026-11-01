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
