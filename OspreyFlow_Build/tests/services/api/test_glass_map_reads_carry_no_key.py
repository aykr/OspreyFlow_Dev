"""No map provider's key, and no key-bearing address, in anything the Glass's map reads (P4's brief:
"never a provider's key or key-bearing URL in the Glass"; ADR-147 decision 2; `00_ARCHITECTURE.md`
§1.2's tile proxy).

The basemap switch (`BasemapSwitch` in `apps/workspace/src/map/MapControls.tsx`) offers the
providers `GET /v1/map/providers` returns that the map can draw, and draws the chosen one from that
answer alone, so what the Glass can hold of a provider is exactly what the map's read routes answer.
Two keys are planted: one entered in *Admin › Maps* through the real key route, one the installer's
`env:` reference resolves. Then every `GET` route under `/v1/map/` (found by walking the app, so a
route added later is walked too) is called for every provider, with the upstream answering a tile
and refusing one; no answer carries either key, the hosted provider's address or a `{credential}`
template. The tile proxy's upstream request carries the key; that is the one place it goes. (The
place search answers places, never a provider: `test_map_places_route.py`.) A provider the browser
fetches may take no key at all, refused as `osprey.yaml` is read (`tests/schemas/test_mapconfig.py`'s
`test_a_provider_the_browser_fetches_takes_no_key`), since its address is the Glass's.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api.app import app, get_principal
from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile
from services.api.tile_proxy import TileFetchFailed

from schemas.domain import Principal
from schemas.mapconfig import MapConfig

ADMIN_KEY = "k-PLANTED-admin-map-key-P4-glass-reads"
ENV_KEY = "k-PLANTED-env-map-key-P4-glass-reads"
ENV_VAR = "OSPREY_TEST_P4_MAP_KEY"
PNG = b"\x89PNG\r\n\x1a\n synthetic tile"
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="u", roles=["osprey-admin"])
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="u", roles=["analyst"])
OSM = {
    "id": "osm-local", "label": "OpenStreetMap", "kind": "vector",
    "source": "file:///data/tiles/gb.pmtiles", "style": "bundled:osprey-dark",
    "attribution": "© OpenStreetMap contributors",
    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
}  # fmt: skip
#: A key entered in Admin.
HOSTED = {
    "id": "hosted-tiles", "label": "Hosted tiles", "kind": "raster",
    "source": "https://tiles.example.test/{z}/{x}/{y}.png?key={credential}",
    "style": "bundled:osprey-raster-overlay", "proxy": "required", "attribution": "Example",
    "licence": {"id": "example", "redistributable": False, "client_scope": "per-deployment"},
}  # fmt: skip
#: The installer's `env:` reference.
INSTALLED = {
    "id": "installed-tiles", "label": "Installed tiles", "kind": "raster",
    "source": "https://installed.example.test/{z}/{x}/{y}.png?apikey={credential}",
    "style": "bundled:osprey-raster-overlay", "proxy": "required", "credential": f"env:{ENV_VAR}",
    "attribution": "Example two",
    "licence": {"id": "example", "redistributable": False, "client_scope": "per-deployment"},
}  # fmt: skip
NEVER = (
    ADMIN_KEY,
    ENV_KEY,
    "tiles.example.test",
    "installed.example.test",
    "{credential}",
    ENV_VAR,
)


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.api import map_admin

    monkeypatch.setattr(map_admin, "resolve_host", lambda host: [])


@pytest.fixture
def admin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MapAdmin]:
    monkeypatch.setenv(ENV_VAR, ENV_KEY)
    folder = tmp_path / "map-settings"
    admin = MapAdmin(
        installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM, INSTALLED]}),
        settings_file=MapSettingsFile(folder),
        key_file=MapKeyFile(folder),
        audit=InMemoryMapAdminAudit(),
        tiles_root=tmp_path / "tiles",
    )
    app.state.map_admin = admin
    monkeypatch.setattr(app.state, "tile_cache_storage", None, raising=False)
    yield admin
    app.dependency_overrides.clear()
    del app.state.map_admin


def _as(principal: Principal) -> TestClient:
    app.dependency_overrides[get_principal] = lambda: principal
    return TestClient(app, raise_server_exceptions=False)


def _map_reads() -> list[str]:
    return sorted(
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/v1/map/")
        and "GET" in route.methods
    )


def test_the_map_routes_walked_are_the_three_the_glass_reads() -> None:
    """The walk below covers what exists: a new map read route is walked by it the day it is
    added."""
    assert _map_reads() == [
        "/v1/map/local-source/{provider_id}",
        "/v1/map/providers",
        "/v1/map/tiles/{provider_id}/{z}/{x}/{y}",
    ]


@pytest.mark.parametrize("upstream", ["answers", "refuses"])
def test_no_key_or_key_bearing_address_in_any_map_answer_the_glass_reads(
    admin: MapAdmin, monkeypatch: pytest.MonkeyPatch, upstream: str
) -> None:
    asked: list[str] = []

    async def fetch(url: str) -> bytes:
        asked.append(url)
        if upstream == "refuses":
            raise TileFetchFailed(403)
        return PNG

    monkeypatch.setattr(app_module, "fetch_tile", fetch)
    as_admin = _as(ADMIN)
    assert (
        as_admin.post(
            "/v1/admin/maps/providers", content=json.dumps({"provider": HOSTED})
        ).status_code
        == 200
    )
    assert (
        as_admin.put(
            "/v1/admin/maps/providers/hosted-tiles/key", content=json.dumps({"key": ADMIN_KEY})
        ).status_code
        == 200
    )

    client = _as(ANALYST)
    providers = client.get("/v1/map/providers")
    assert providers.status_code == 200
    ids = [p["id"] for p in providers.json()["providers"]]
    assert ids == ["osm-local", "installed-tiles", "hosted-tiles"]
    answers = [providers]
    for path in _map_reads():
        for provider_id in [*ids, "nowhere"]:
            url = path.replace("{provider_id}", provider_id).replace("{z}/{x}/{y}", "1/2/3")
            answers.append(client.get(url))
    for answer in answers:
        body = answer.content
        for never in NEVER:
            assert never.encode() not in body, (answer.request.url, never, answer.text[:300])
    # The keys went upstream and only there: each hosted provider was asked once for its tile.
    assert sorted(asked) == [
        f"https://installed.example.test/1/2/3.png?apikey={ENV_KEY}",
        f"https://tiles.example.test/1/2/3.png?key={ADMIN_KEY}",
    ]
    tiles = [a for a in answers if "/v1/map/tiles/" in str(a.request.url) and a.status_code == 200]
    assert len(tiles) == (2 if upstream == "answers" else 0)
