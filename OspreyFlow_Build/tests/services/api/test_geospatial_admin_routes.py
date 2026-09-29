"""`POST /v1/admin/geospatial/build-basemap` and `POST /v1/admin/geospatial/verify` — round 09's
own resolution of `harness/geospatial.py`'s "not reachable from inside the harness image" finding:
these two actions live here, in the one process that already has `services`/`adapters` available,
admin-role-gated the same way `06_DECISIONS.md` ruling R2 already gates the harness's own `/admin`
(same role name, same audience check — a bearer token good for one is good for both).

**Access control shown red first** (`CLAUDE.md` rule 4): `test_require_admin_role_refuses_a_
principal_without_the_role` is the dependency-level case (mirrors `test_studio_roles.py`'s own
discipline for `require_studio_role` — exercised directly, no route needed to prove it), and
`test_*_route_refuses_without_the_admin_role` is the route-level case for each of the two routes,
proven against the real `TestClient`/real middleware stack, not only the bare dependency.

`build_local_basemap` itself needs a real Geofabrik download, a real `planetiler.jar` and Java —
none of which exist in this tree (`round 03`'s own finding, unchanged: `find . -iname
"*.pmtiles"` returns nothing). What is tested here is the *route's own wiring* — SSE streaming in
Launch's own shape, audit recording, error propagation — with `services.api.app.build_local_
basemap` itself replaced by a fake that calls the same `progress` callback and returns the same
`BasemapBuildResult` shape, the same "prove the wiring, not the external pipeline" boundary
`tests/harness/test_webapp_launch.py` already draws for `harness.apply`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from services.api.app import (
    ADMIN_ROLE,
    app,
    get_audit,
    get_config,
    get_graph,
    get_map_config,
    get_ontology,
    get_principal,
    require_admin_role,
)

from schemas.domain import Principal, TxId
from schemas.mapconfig import MapConfig, MapProvider

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", roles=[ADMIN_ROLE])
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _principal(*roles: str) -> Principal:
    return Principal(id="p-1", clearance="OFFICIAL", org_unit="unit-1", roles=list(roles))


def _minimal_map_config() -> MapConfig:
    """`MapConfig` requires at least one provider and a `default` naming a real one — there is
    no such thing as an empty map config, so tests that do not care about its content still need
    a minimally valid one."""
    provider = MapProvider.model_validate(
        {
            "id": "osm-local",
            "label": "OpenStreetMap",
            "kind": "vector",
            "source": "file:///tmp/does-not-matter.pmtiles",
            "attribution": "© OpenStreetMap contributors",
            "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
        }
    )
    return MapConfig(default="osm-local", providers=[provider])


async def test_require_admin_role_refuses_a_principal_without_the_role() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await require_admin_role(_principal())
    assert excinfo.value.status_code == 403


async def test_require_admin_role_returns_the_principal_that_holds_it() -> None:
    principal = _principal(ADMIN_ROLE)
    assert await require_admin_role(principal) is principal


class _FakeGraph:
    """Only `begin_transaction`/`commit_transaction`/`rollback_transaction` — the build-basemap
    route's own use of `GraphDep` — never a real store; `build_local_basemap` itself is replaced
    for these tests, so nothing here ever reads or writes a real graph."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def begin_transaction(self) -> TxId:
        return "tx-1"

    async def commit_transaction(self, tx: TxId) -> None:
        self.committed = True

    async def rollback_transaction(self, tx: TxId) -> None:
        self.rolled_back = True


class _FakeConfig:
    osprey_config_path = "osprey.yaml"


def _events(response_text: str) -> list[dict[str, Any]]:
    import json

    events = []
    for block in response_text.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[len("data: ") :]))
    return events


@pytest.fixture
def graph() -> _FakeGraph:
    return _FakeGraph()


@pytest.fixture
def client(graph: _FakeGraph) -> TestClient:
    app.dependency_overrides[get_principal] = lambda: ADMIN
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_ontology] = lambda: object()
    app.dependency_overrides[get_config] = lambda: _FakeConfig()
    app.dependency_overrides[get_audit] = lambda: _RecordingAudit()
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


class _RecordingAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def test_build_basemap_route_refuses_without_the_admin_role(graph: _FakeGraph) -> None:
    app.dependency_overrides[get_principal] = lambda: ANALYST
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_ontology] = lambda: object()
    app.dependency_overrides[get_config] = lambda: _FakeConfig()
    app.dependency_overrides[get_audit] = lambda: _RecordingAudit()
    try:
        response = TestClient(app).post(
            "/v1/admin/geospatial/build-basemap",
            json={
                "region": "great-britain",
                "output_dir": "/tmp/x",
                "planetiler_jar_path": "/tmp/p.jar",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403


def test_verify_map_route_refuses_without_the_admin_role() -> None:
    app.dependency_overrides[get_principal] = lambda: ANALYST
    app.dependency_overrides[get_map_config] = lambda: _minimal_map_config()
    app.dependency_overrides[get_audit] = lambda: _RecordingAudit()
    try:
        response = TestClient(app).post("/v1/admin/geospatial/verify")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403


def test_build_basemap_route_refuses_an_unknown_region(client: TestClient) -> None:
    response = client.post(
        "/v1/admin/geospatial/build-basemap",
        json={"region": "narnia", "output_dir": "/tmp/x", "planetiler_jar_path": "/tmp/p.jar"},
    )
    assert response.status_code == 422
    assert "narnia" in response.json()["detail"]


def test_build_basemap_route_streams_real_progress_and_completes(
    client: TestClient, graph: _FakeGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.api.app import BasemapBuildResult

    class _FakeReport:
        nodes_created = 12
        nodes_referenced = 3
        rejections: list[str] = []

    async def _fake_build(*, progress: Any, **_kwargs: Any) -> BasemapBuildResult:
        progress("Downloading the 'great-britain' Geofabrik extract...")
        progress("Running planetiler...")
        progress("Loading the OSM-derived gazetteer...")
        return BasemapBuildResult(
            pmtiles_path=Path("/tmp/great-britain.pmtiles"),
            gazetteer_report=_FakeReport(),  # type: ignore[arg-type]
            map_config=_minimal_map_config(),
        )

    monkeypatch.setattr("services.api.app.build_local_basemap", _fake_build)

    response = client.post(
        "/v1/admin/geospatial/build-basemap",
        json={
            "region": "great-britain",
            "output_dir": "/tmp/x",
            "planetiler_jar_path": "/tmp/p.jar",
        },
    )

    assert response.status_code == 200
    events = _events(response.text)
    lines = [e["line"] for e in events if "line" in e]
    assert "Running planetiler..." in lines
    assert "event: complete" in response.text
    assert '"returncode": 0' in response.text
    assert "great-britain.pmtiles" in response.text
    assert graph.committed and not graph.rolled_back


def test_build_basemap_route_rolls_back_and_reports_a_real_failure(
    client: TestClient, graph: _FakeGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_build_that_fails(*, progress: Any, **_kwargs: Any) -> None:
        progress("Downloading the 'great-britain' Geofabrik extract...")
        raise RuntimeError("no planetiler.jar at /tmp/p.jar")

    monkeypatch.setattr("services.api.app.build_local_basemap", _fake_build_that_fails)

    response = client.post(
        "/v1/admin/geospatial/build-basemap",
        json={
            "region": "great-britain",
            "output_dir": "/tmp/x",
            "planetiler_jar_path": "/tmp/p.jar",
        },
    )

    assert response.status_code == 200
    assert '"returncode": 1' in response.text
    assert "no planetiler.jar" in response.text
    assert graph.rolled_back and not graph.committed


def test_verify_map_route_reports_the_real_verify_map_result() -> None:
    provider = MapProvider.model_validate(
        {
            "id": "osm-local",
            "label": "OpenStreetMap",
            "kind": "vector",
            "source": "file:///tmp/does-not-matter.pmtiles",
            "attribution": "© OpenStreetMap contributors",
            "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
        }
    )
    app.dependency_overrides[get_principal] = lambda: ADMIN
    app.dependency_overrides[get_map_config] = lambda: MapConfig(
        default="osm-local", providers=[provider]
    )
    app.dependency_overrides[get_audit] = lambda: _RecordingAudit()
    try:
        response = TestClient(app).post("/v1/admin/geospatial/verify")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["issues"] == []


def test_verify_map_route_reports_a_real_attribution_issue() -> None:
    provider = MapProvider.model_validate(
        {
            "id": "osm-local",
            "label": "OpenStreetMap",
            "kind": "vector",
            "source": "file:///tmp/does-not-matter.pmtiles",
            "attribution": "",
            "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
        }
    )
    app.dependency_overrides[get_principal] = lambda: ADMIN
    app.dependency_overrides[get_map_config] = lambda: MapConfig(
        default="osm-local", providers=[provider]
    )
    app.dependency_overrides[get_audit] = lambda: _RecordingAudit()
    try:
        response = TestClient(app).post("/v1/admin/geospatial/verify")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["issues"][0]["check"] == "attribution"
