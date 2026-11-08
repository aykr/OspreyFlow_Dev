"""*Admin › Maps*' routes (`06_DECISIONS.md` ADR-147), through the real app, the real right check
and the real logger:

- rule 4: every `/v1/admin/maps` and `/v1/admin/geospatial` route, found by walking the app's own
  routes (so a route added later is walked too), refuses a principal without `manage_geospatial`,
  an administrator holding every other administration right included, and changes nothing;
- the key (ADR-135 Amendment 2's rule): a recognisable planted key, sent through the real key route,
  and planted in a malformed body, a refused provider and an unknown provider's key route, is in no
  response, log record, audit entry or maps file; it reaches the tile proxy's upstream request only;
- the map follows *Admin › Maps* with no restart: `/v1/map/providers` lists a provider added there;
- a provider that needs a key and holds none answers its tiles in words, never an address.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api.app import app, get_principal
from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile

from schemas.domain import Principal
from schemas.mapconfig import MapConfig

PLANTED = "k-PLANTED-map-route-key-W4R2-do-not-leak"
PNG = b"\x89PNG\r\n\x1a\n synthetic tile"
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="u", roles=["osprey-admin"])
MAPS_ONLY = Principal(
    id="g-1", clearance="OFFICIAL", org_unit="u", roles=["right:manage_geospatial"]
)
#: Every administration right but this one, granted singly, and the admin role the geospatial
#: build and verify also check (kept, the orchestrator's settlement of 8 November).
EVERY_OTHER_ADMIN_RIGHT = Principal(
    id="admin-2",
    clearance="OFFICIAL",
    org_unit="u",
    roles=[
        f"right:{r}"
        for r in ("administer_system", "manage_people", "manage_models", "read_audit")
    ],
)
OSM = {
    "id": "osm-local", "label": "OpenStreetMap", "kind": "vector",
    "source": "file:///data/tiles/gb.pmtiles", "style": "bundled:osprey-dark",
    "attribution": "© OpenStreetMap contributors",
    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
}  # fmt: skip
HOSTED = {
    "id": "hosted-tiles", "label": "Hosted tiles", "kind": "raster",
    "source": "https://tiles.example.test/{z}/{x}/{y}.png?key={credential}",
    "proxy": "required", "attribution": "Example",
    "licence": {"id": "example", "redistributable": False, "client_scope": "per-deployment"},
}  # fmt: skip
#: A body for each route the walk calls, so a refusal is the right check's and not the body's.
BODIES: dict[str, Any] = {
    "/v1/admin/maps/providers": {"provider": HOSTED},
    "/v1/admin/maps/providers/{provider_id}": {"provider": OSM},
    "/v1/admin/maps/providers/{provider_id}/key": {"key": PLANTED},
    "/v1/admin/maps/default": {"default": "osm-local"},
    "/v1/admin/maps/areas": {"areas": []},
    "/v1/admin/maps/schedule": {"schedule": {"every_hours": 6}},
    "/v1/admin/geospatial/build-basemap": {"region": "rutland"},
}


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.folder = tmp_path / "map-settings"
        self.audit = InMemoryMapAdminAudit()
        self.admin = MapAdmin(
            installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM]}),
            settings_file=MapSettingsFile(self.folder),
            key_file=MapKeyFile(self.folder),
            audit=self.audit,
            tiles_root=tmp_path / "tiles",
        )

    def kept(self) -> str:
        files = "".join(
            p.read_text() for p in self.folder.glob("*.yaml") if p.name != "map-keys.yaml"
        )
        return files + "".join(e.model_dump_json() for e in self.audit.entries)


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    w = World(tmp_path)
    app.state.map_admin = w.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield w
    app.dependency_overrides.clear()
    del app.state.map_admin


def _as(principal: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: principal


def _maps_routes() -> list[tuple[str, str]]:
    found = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(
            ("/v1/admin/maps", "/v1/admin/geospatial")
        ):
            found.extend((method, route.path) for method in sorted(route.methods))
    return found


def _call(client: TestClient, method: str, path: str) -> Any:
    url = path.replace("{provider_id}", "hosted-tiles")
    body = BODIES.get(path)
    if method in {"GET", "DELETE"} or body is None:
        return client.request(method, url)
    return client.request(method, url, content=json.dumps(body))


def test_the_walk_finds_every_maps_route() -> None:
    """Not vacuous: the walk below covers at least these (a removed one fails here)."""
    found = set(_maps_routes())
    for expected in [
        ("GET", "/v1/admin/maps"), ("GET", "/v1/admin/maps/history"),
        ("POST", "/v1/admin/maps/providers"), ("PUT", "/v1/admin/maps/providers/{provider_id}"),
        ("DELETE", "/v1/admin/maps/providers/{provider_id}"),
        ("PUT", "/v1/admin/maps/providers/{provider_id}/key"),
        ("DELETE", "/v1/admin/maps/providers/{provider_id}/key"),
        ("PUT", "/v1/admin/maps/default"), ("PUT", "/v1/admin/maps/areas"),
        ("PUT", "/v1/admin/maps/schedule"), ("POST", "/v1/admin/maps/prefetch"),
        ("POST", "/v1/admin/geospatial/build-basemap"), ("POST", "/v1/admin/geospatial/verify"),
    ]:  # fmt: skip
        assert expected in found, expected


@pytest.mark.parametrize("principal", [EVERY_OTHER_ADMIN_RIGHT], ids=["every-other-admin-right"])
def test_every_maps_route_refuses_a_principal_without_manage_geospatial(
    world: World, principal: Principal
) -> None:
    _as(principal)
    client = TestClient(app, raise_server_exceptions=False)
    for method, path in _maps_routes():
        response = _call(client, method, path)
        assert response.status_code == 403, (method, path, response.status_code)
        assert response.json()["detail"] == {
            "error": "right_required", "right": "manage_geospatial"
        }, (method, path)  # fmt: skip
    assert not world.folder.exists() and world.audit.entries == []


def test_a_holder_of_manage_geospatial_alone_manages_the_maps(world: World) -> None:
    _as(MAPS_ONLY)
    client = TestClient(app)
    added = client.post("/v1/admin/maps/providers", content=json.dumps({"provider": HOSTED}))
    assert added.status_code == 200, added.text
    assert [p["provider"]["id"] for p in added.json()["providers"]] == ["osm-local", "hosted-tiles"]
    # Build and verify also check the admin role (kept, the orchestrator's settlement).
    assert client.post("/v1/admin/geospatial/verify").status_code == 403


def test_a_planted_key_is_in_no_response_log_audit_or_maps_file(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = TestClient(app, raise_server_exceptions=False)
    answers = [client.post("/v1/admin/maps/providers", content=json.dumps({"provider": HOSTED}))]
    answers.append(client.put("/v1/admin/maps/providers/hosted-tiles/key",
                              content=json.dumps({"key": PLANTED})))  # fmt: skip
    # The plants that a careless route would echo: a malformed body, an unknown provider, a refused
    # provider (the key pasted into its credential and into its label's place), a provider that
    # takes no key.
    answers += [
        client.put("/v1/admin/maps/providers/hosted-tiles/key",
                   content=json.dumps({"key": PLANTED, "extra": PLANTED})),
        client.put("/v1/admin/maps/providers/hosted-tiles/key", content=PLANTED),
        client.put("/v1/admin/maps/providers/nowhere/key", content=json.dumps({"key": PLANTED})),
        client.put("/v1/admin/maps/providers/osm-local/key", content=json.dumps({"key": PLANTED})),
        client.post("/v1/admin/maps/providers", content=json.dumps(
            {"provider": {**HOSTED, "id": "other", "credential": PLANTED}})),
        client.post("/v1/admin/maps/providers", content=json.dumps(
            {"provider": {**HOSTED, "id": "other", "credential_param": PLANTED}})),
        client.get("/v1/admin/maps"),
        client.get("/v1/admin/maps/history"),
        client.get("/v1/map/providers"),
    ]  # fmt: skip
    statuses = [a.status_code for a in answers]
    assert statuses == [200, 200, 422, 422, 404, 409, 422, 422, 200, 200, 200], statuses
    for answer in answers:
        assert PLANTED not in answer.text, answer.text
    assert all(PLANTED not in r.getMessage() for r in caplog.records)
    assert PLANTED not in world.kept()
    assert world.admin.key_for("hosted-tiles") == PLANTED
    view = answers[-3].json()
    assert next(p for p in view["providers"] if p["provider"]["id"] == "hosted-tiles")[
        "key_state"
    ] == "set"
    assert [e.action for e in world.audit.entries] == ["provider_added", "key_set"]


def test_the_tile_proxy_carries_the_admin_key_upstream_and_nowhere_else(
    world: World, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    asked: list[str] = []

    async def fetch(url: str) -> bytes:
        asked.append(url)
        return PNG

    monkeypatch.setattr(app_module, "fetch_tile", fetch)
    # The provider keeps no cache, so the route never reaches its storage.
    monkeypatch.setattr(app.state, "tile_cache_storage", None, raising=False)
    client = TestClient(app, raise_server_exceptions=False)
    client.post("/v1/admin/maps/providers", content=json.dumps({"provider": HOSTED}))

    refused = client.get("/v1/map/tiles/hosted-tiles/1/2/3")
    assert refused.status_code == 503 and "Admin › Maps" in refused.json()["detail"]
    assert "tiles.example.test" not in refused.text and asked == []

    client.put("/v1/admin/maps/providers/hosted-tiles/key", content=json.dumps({"key": PLANTED}))
    tile = client.get("/v1/map/tiles/hosted-tiles/1/2/3")

    assert tile.status_code == 200 and tile.content == PNG
    assert asked == [f"https://tiles.example.test/1/2/3.png?key={PLANTED}"]
    assert PLANTED not in tile.text and PLANTED not in json.dumps(dict(tile.headers))
    assert all(PLANTED not in r.getMessage() for r in caplog.records)


def test_the_map_follows_a_change_in_admin_with_no_restart(world: World) -> None:
    client = TestClient(app)
    before = client.get("/v1/map/providers").json()
    client.post("/v1/admin/maps/providers", content=json.dumps({"provider": HOSTED}))
    client.put("/v1/admin/maps/default", content=json.dumps({"default": "hosted-tiles"}))
    after = client.get("/v1/map/providers").json()
    assert [p["id"] for p in before["providers"]] == ["osm-local"]
    assert [p["id"] for p in after["providers"]] == ["osm-local", "hosted-tiles"]
    assert after["default"] == "hosted-tiles"


def test_an_area_over_the_cap_is_refused_in_words_through_the_route(world: World) -> None:
    client = TestClient(app)
    client.post("/v1/admin/maps/providers", content=json.dumps(
        {"provider": {**HOSTED, "cache": {"ttl_days": 30}}}))  # fmt: skip
    big = {"name": "Everywhere", "provider_id": "hosted-tiles", "west": -10, "south": 49,
           "east": 3, "north": 60, "zoom_min": 0, "zoom_max": 15}  # fmt: skip
    answer = client.put("/v1/admin/maps/areas", content=json.dumps({"areas": [big]}))
    assert answer.status_code == 422
    assert "tiles over its zooms" in answer.json()["detail"]["detail"]
