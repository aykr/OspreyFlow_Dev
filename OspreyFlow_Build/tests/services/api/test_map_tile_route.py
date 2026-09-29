"""`GET /v1/map/tiles/{provider_id}/{z}/{x}/{y}` route wiring —
`spec/00_ARCHITECTURE.md` §1.2's tile proxy. Mirrors `test_sites_routes.py`'s own discipline:
dependency overrides and monkeypatched module-level helpers, never a live
network call or live MinIO — `build_upstream_url`/`fetch_tile`'s own
correctness is proven in `test_tile_proxy.py`, `read_cached_tile`/
`write_cached_tile`'s in `test_tile_cache.py`; what belongs here is only
"does the right dependency's result end up in the right response, with
the right status code."
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_map_config, get_principal, get_tile_cache_storage

from schemas.domain import Principal
from schemas.mapconfig import MapConfig, MapProvider

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")

_PROXIED_WITH_CACHE = MapProvider.model_validate(
    {
        "id": "usgs-national-map",
        "label": "USGS The National Map",
        "kind": "raster",
        "service": "wmts",
        "endpoint": "https://basemap.nationalmap.gov/arcgis/rest/services/wmts",
        "layer": "USGSTopo",
        "tile_matrix_set": "GoogleMapsCompatible",
        "format": "image/png",
        "wmts_style": "default",
        "proxy": "recommended",
        "cache": {"ttl_days": 30, "prefetch_areas": []},
        "attribution": "USGS The National Map",
        "licence": {"id": "usgs-public-domain", "redistributable": True, "client_scope": "open"},
    }
)
_PROXIED_NO_CACHE = MapProvider.model_validate(
    {
        "id": "no-cache-provider",
        "label": "No-cache provider",
        "kind": "raster",
        "service": "wmts",
        "endpoint": "https://example.test/wmts",
        "layer": "default-layer",
        "tile_matrix_set": "GoogleMapsCompatible",
        "format": "image/png",
        "wmts_style": "default",
        "proxy": "required",
        "attribution": "Example",
        "licence": {"id": "example", "redistributable": True, "client_scope": "open"},
    }
)
_NOT_PROXIED = MapProvider.model_validate(
    {
        "id": "osm-local",
        "label": "OpenStreetMap",
        "kind": "vector",
        "source": "file:///data/tiles/osm-local.pmtiles",
        "attribution": "© OpenStreetMap contributors",
        "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
    }
)
_CONFIG = MapConfig(
    default="osm-local", providers=[_PROXIED_WITH_CACHE, _PROXIED_NO_CACHE, _NOT_PROXIED]
)

_PNG_BYTES = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    fetch_calls: list[str] = []
    read_cache_calls: list[str] = []
    write_cache_calls: list[str] = []

    async def fake_fetch_tile(url: str) -> bytes:
        fetch_calls.append(url)
        return _PNG_BYTES

    def fake_read_cached_tile(*, storage: object, object_key: str, ttl_days: int) -> bytes | None:
        read_cache_calls.append(object_key)
        return None

    def fake_write_cached_tile(data: bytes, *, storage: object, object_key: str) -> None:
        write_cache_calls.append(object_key)

    monkeypatch.setattr("services.api.app.fetch_tile", fake_fetch_tile)
    monkeypatch.setattr("services.api.app.read_cached_tile", fake_read_cached_tile)
    monkeypatch.setattr("services.api.app.write_cached_tile", fake_write_cached_tile)

    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_map_config] = lambda: _CONFIG
    app.dependency_overrides[get_tile_cache_storage] = lambda: object()

    test_client = TestClient(app)
    test_client.fetch_calls = fetch_calls  # type: ignore[attr-defined]
    test_client.read_cache_calls = read_cache_calls  # type: ignore[attr-defined]
    test_client.write_cache_calls = write_cache_calls  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_fetches_and_caches_a_tile_on_a_cache_miss(client: TestClient) -> None:
    response = client.get("/v1/map/tiles/usgs-national-map/5/10/15")

    assert response.status_code == 200
    assert response.content == _PNG_BYTES
    assert response.headers["content-type"] == "image/png"
    assert client.read_cache_calls == ["tiles/usgs-national-map/5/10/15"]
    assert client.fetch_calls == [
        "https://basemap.nationalmap.gov/arcgis/rest/services/wmts"
        "?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        "&LAYER=USGSTopo&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible"
        "&TILEMATRIX=5&TILEROW=15&TILECOL=10&FORMAT=image/png"
    ]
    assert client.write_cache_calls == ["tiles/usgs-national-map/5/10/15"]


def test_skips_the_cache_entirely_when_the_provider_declares_no_cache(client: TestClient) -> None:
    response = client.get("/v1/map/tiles/no-cache-provider/1/2/3")

    assert response.status_code == 200
    assert client.read_cache_calls == []
    assert client.write_cache_calls == []
    assert client.fetch_calls == [
        "https://example.test/wmts"
        "?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        "&LAYER=default-layer&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible"
        "&TILEMATRIX=1&TILEROW=3&TILECOL=2&FORMAT=image/png"
    ]


def test_404s_for_an_unknown_provider(client: TestClient) -> None:
    response = client.get("/v1/map/tiles/does-not-exist/0/0/0")

    assert response.status_code == 404


def test_400s_for_a_provider_that_is_not_proxied(client: TestClient) -> None:
    response = client.get("/v1/map/tiles/osm-local/0/0/0")

    assert response.status_code == 400
    assert client.fetch_calls == []
