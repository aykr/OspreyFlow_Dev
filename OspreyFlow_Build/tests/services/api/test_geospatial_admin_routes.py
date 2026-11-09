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

Since ADR-147 the build route takes a named region only and runs
`services.api.map_admin.build_basemap`, which needs a Geofabrik download, a planetiler jar and Java,
none of which a CI runner holds. What is tested here is the route's own wiring (SSE streaming in
Launch's own shape, the audit, the graph transaction committed or rolled back, no server path taken
from the caller) with the build or its download and planetiler run replaced, the boundary
`tests/harness/test_webapp_launch.py` draws for `harness.apply`; the real gazetteer load is
`tests/ingest/test_map_admin_build_end_to_end.py`'s.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from services.api.app import (
    ADMIN_ROLE,
    app,
    get_analytics,
    get_audit,
    get_config,
    get_datasets,
    get_graph,
    get_handling_scheme,
    get_map_config,
    get_ontology,
    get_principal,
    require_admin_role,
)
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile

from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal, TxId
from schemas.mapconfig import MapConfig, MapProvider

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", roles=[ADMIN_ROLE])
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
#: The analytics store and the dataset store the build route is handed (ADR-147 Amendment 1: the
#: gazetteer's points and its dataset); a sentinel and the in-memory store, read back below.
ANALYTICS = object()
DATASETS = InMemoryDatasetStore()


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
def map_admin(tmp_path: Path) -> Iterator[MapAdmin]:
    """ADR-147: the build registers its provider in the maps file, through the app's `MapAdmin`."""
    (tmp_path / "tiles" / "planetiler").mkdir(parents=True)
    (tmp_path / "tiles" / "planetiler" / "planetiler.jar").write_bytes(b"PK synthetic jar")
    admin = MapAdmin(
        installed=_minimal_map_config(), settings_file=MapSettingsFile(tmp_path / "maps"),
        key_file=MapKeyFile(tmp_path / "maps"), audit=InMemoryMapAdminAudit(),
        tiles_root=tmp_path / "tiles", java=lambda _name: "/usr/bin/java",
    )  # fmt: skip
    app.state.map_admin = admin
    yield admin
    del app.state.map_admin


@pytest.fixture
def client(graph: _FakeGraph, map_admin: MapAdmin) -> TestClient:
    app.dependency_overrides[get_principal] = lambda: ADMIN
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_ontology] = lambda: object()
    app.dependency_overrides[get_config] = lambda: _FakeConfig()
    app.dependency_overrides[get_audit] = lambda: _RecordingAudit()
    app.dependency_overrides[get_analytics] = lambda: ANALYTICS
    app.dependency_overrides[get_datasets] = lambda: DATASETS
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
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
            json={"region": "great-britain"},
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
        json={"region": "narnia"},
    )
    assert response.status_code == 422
    assert "narnia" in response.json()["detail"]


def _fake_gazetteer(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    class _FakeReport:
        nodes_created = 12
        nodes_referenced = 3
        rejections: list[str] = []

    loads: list[dict[str, Any]] = []

    async def _load(*_args: Any, **kwargs: Any) -> _FakeReport:
        loads.append(kwargs)
        return _FakeReport()

    monkeypatch.setattr("services.api.app.load_gazetteer", _load)
    return loads


def test_the_build_loads_the_places_into_the_regions_gazetteer_dataset_with_their_points(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-147 Amendment 1 (the orchestrator's settlement, 9 November 2026): the places go into
    `gazetteer-osm-<region>`, registered in the dataset store for the recipe's unit, so a case's
    Author can add it to a case; and their points go into the Conduit's analytics store, so a place
    search can take the map to them."""
    loads = _fake_gazetteer(monkeypatch)

    async def _fake_build(admin: Any, *, load_places: Any, settle: Any, **_kwargs: Any) -> Any:
        counts = await load_places(Path("/tmp/rutland.osm.pbf"))
        await settle()
        return ("rutland.pmtiles", *counts)

    monkeypatch.setattr("services.api.map_admin.build_basemap", _fake_build)
    response = client.post("/v1/admin/geospatial/build-basemap", json={"region": "rutland"})
    assert '"returncode": 0' in response.text, response.text
    assert [(load["dataset"], load["analytics"]) for load in loads] == [
        ("gazetteer-osm-rutland", ANALYTICS)
    ]
    held = DATASETS.datasets["gazetteer-osm-rutland"]
    assert (held.owning_unit, held.created_by) == ("unit-1", "admin-1")


def test_the_build_s_unit_is_a_setting_and_an_unknown_one_is_refused_in_words_before_anything(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-147 Amendment 2 (the owner's ruling 8): the gazetteer's unit is the build's setting, no
    longer the recipe's `unit-1`. A unit holding no case and no dataset here is refused in words,
    before the extract is fetched or a place written; a unit that holds one is the unit of the
    places and of their dataset."""
    loads = _fake_gazetteer(monkeypatch)
    built: list[str] = []

    async def _fake_build(admin: Any, *, load_places: Any, settle: Any, **_kwargs: Any) -> Any:
        built.append("built")
        counts = await load_places(Path("/tmp/rutland.osm.pbf"))
        await settle()
        return ("rutland.pmtiles", *counts)

    monkeypatch.setattr("services.api.map_admin.build_basemap", _fake_build)
    refused = client.post(
        "/v1/admin/geospatial/build-basemap", json={"region": "rutland", "unit": "unit-nowhere"}
    )
    assert refused.status_code == 422
    assert refused.json()["detail"].startswith(
        "No case or dataset in this deployment is held by the unit 'unit-nowhere'"
    )
    assert (built, loads) == ([], [])

    DATASETS.datasets["d-unit-7"] = Dataset(
        id="d-unit-7", name="Unit 7's", owning_unit="unit-7", created_at=datetime.now(UTC),
        created_by="someone",
    )  # fmt: skip
    DATASETS.datasets.pop("gazetteer-osm-rutland", None)
    try:
        response = client.post(
            "/v1/admin/geospatial/build-basemap", json={"region": "rutland", "unit": "unit-7"}
        )
        assert '"returncode": 0' in response.text, response.text
        assert [load["unit"] for load in loads] == ["unit-7"]
        assert DATASETS.datasets["gazetteer-osm-rutland"].owning_unit == "unit-7"
        # Built for unit-7, so a rebuild for the administrator's own unit is refused in words.
        again = client.post("/v1/admin/geospatial/build-basemap", json={"region": "rutland"})
        assert again.status_code == 422
        assert "held by the unit 'unit-7'" in again.json()["detail"]
        assert len(loads) == 1
    finally:
        DATASETS.datasets.pop("d-unit-7", None)
        DATASETS.datasets.pop("gazetteer-osm-rutland", None)


def test_build_basemap_route_streams_real_progress_and_completes(
    client: TestClient, graph: _FakeGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_gazetteer(monkeypatch)

    async def _fake_build(
        admin: Any, *, progress: Any, load_places: Any, settle: Any, **_kwargs: Any
    ) -> tuple[str, int, int, int]:
        progress("Downloading the 'great-britain' Geofabrik extract...")
        progress("Running planetiler...")
        progress("Loading the OSM-derived gazetteer...")
        counts = await load_places(Path("/tmp/great-britain.osm.pbf"))
        await settle()  # as `map_admin.build_basemap` does, before it registers the provider
        return ("great-britain.pmtiles", *counts)

    monkeypatch.setattr("services.api.map_admin.build_basemap", _fake_build)

    response = client.post("/v1/admin/geospatial/build-basemap", json={"region": "great-britain"})

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
    _fake_gazetteer(monkeypatch)

    async def _fake_build_that_fails(
        admin: Any, *, progress: Any, load_places: Any, **_kwargs: Any
    ) -> None:
        progress("Downloading the 'great-britain' Geofabrik extract...")
        await load_places(Path("/tmp/great-britain.osm.pbf"))
        raise RuntimeError("planetiler stopped")

    monkeypatch.setattr("services.api.map_admin.build_basemap", _fake_build_that_fails)

    response = client.post("/v1/admin/geospatial/build-basemap", json={"region": "great-britain"})

    assert response.status_code == 200
    assert '"returncode": 1' in response.text
    # The independent review's minor 8: the error's own words (a path, a provider's answer) are the
    # Conduit's log's, never the Glass's; the person is told it stopped, and by which kind of error.
    assert "planetiler stopped" not in response.text
    assert "The build stopped (RuntimeError)" in response.text
    assert graph.rolled_back and not graph.committed


def test_build_basemap_route_takes_no_server_path_from_the_glass(client: TestClient) -> None:
    """ADR-147: the tiles folder and the jar are the deployment's own; a body naming either is
    refused, so no browser chooses where the Conduit writes or what it runs."""
    response = client.post("/v1/admin/geospatial/build-basemap", json={
        "region": "rutland", "output_dir": "/etc", "planetiler_jar_path": "/tmp/evil.jar",
    })  # fmt: skip
    assert response.status_code == 422
    assert "/etc" not in response.text and "evil" not in response.text


def test_the_real_build_on_a_small_synthetic_region_through_the_route(
    client: TestClient, graph: _FakeGraph, map_admin: MapAdmin, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`map_admin.build_basemap` itself, through the route: a synthetic PBF-headed extract (never
    downloaded, rule 9), planetiler's run standing in for the jar this machine does not hold
    (`P3_RED_RECORD.md`), the gazetteer loader counted; the provider lands in the maps file as tier
    1 and the map serves it with no restart."""
    import scripts.build_local_basemap as basemap_script

    _fake_gazetteer(monkeypatch)
    jars: list[Path] = []

    def downloader(region: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00\x00\x00\x0d\x0a\x09OSMHeader synthetic")
        return dest

    def planetiler(extract: Path, output: Path, *, jar_path: Path) -> Path:
        jars.append(jar_path)
        output.write_bytes(b"PMTiles\x03 synthetic")
        return output

    monkeypatch.setattr(basemap_script, "download_extract", downloader)
    monkeypatch.setattr(basemap_script, "run_planetiler", planetiler)

    response = client.post("/v1/admin/geospatial/build-basemap", json={"region": "rutland"})

    assert '"returncode": 0' in response.text, response.text
    assert (map_admin.tiles_root / "built" / "rutland.pmtiles").is_file()
    assert jars == [map_admin.tiles_root / "planetiler" / "planetiler.jar"]
    provider = map_admin.provider("osm-local-rutland")
    assert provider.source == "file:///data/tiles/built/rutland.pmtiles"
    assert provider.licence.client_scope == "open" and graph.committed
    listed = client.get("/v1/map/providers").json()
    assert "osm-local-rutland" in [p["id"] for p in listed["providers"]]


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


def test_the_places_are_committed_before_the_provider_is_registered(
    client: TestClient, graph: _FakeGraph, map_admin: MapAdmin, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The independent review's minor 9: a provider registered before its places are committed
    would point the map at a basemap whose gazetteer a failed commit then lost."""
    import scripts.build_local_basemap as basemap_script

    _fake_gazetteer(monkeypatch)
    order: list[str] = []

    async def commit(tx: TxId) -> None:
        order.append("commit")

    graph.commit_transaction = commit  # type: ignore[method-assign]
    real_register = map_admin.register_local

    async def register(*args: Any, **kwargs: Any) -> None:
        order.append("register")
        await real_register(*args, **kwargs)

    monkeypatch.setattr(map_admin, "register_local", register)

    def downloader(region: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00\x00\x00\x0d\x0a\x09OSMHeader synthetic")
        return dest

    monkeypatch.setattr(basemap_script, "download_extract", downloader)
    monkeypatch.setattr(basemap_script, "run_planetiler",
                        lambda e, o, *, jar_path: o.write_bytes(b"PMTiles") and o)  # fmt: skip
    response = client.post("/v1/admin/geospatial/build-basemap", json={"region": "rutland"})
    assert '"returncode": 0' in response.text, response.text
    assert order == ["commit", "register"]
