"""`GET /v1/map/local-source/{provider_id}` — Stage 3a's own rehearsal finding, 23 September
2026: the Glass cannot fetch a `file://` URI at all, so a tier-1/2 provider's local PMTiles
source must be served over HTTP by the Conduit. Mirrors `test_map_tile_route.py`'s own
discipline: dependency overrides, a real temp file rather than a live basemap build.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_map_config, get_principal

from schemas.domain import Principal
from schemas.mapconfig import MapConfig, MapProvider

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _config_for(tmp_path: Path) -> tuple[MapConfig, Path]:
    pmtiles_path = tmp_path / "osm-local.pmtiles"
    provider = MapProvider.model_validate(
        {
            "id": "osm-local",
            "label": "OpenStreetMap",
            "kind": "vector",
            "source": f"file://{pmtiles_path}",
            "attribution": "© OpenStreetMap contributors",
            "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
        }
    )
    proxied = MapProvider.model_validate(
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
            "attribution": "USGS The National Map",
            "licence": {
                "id": "usgs-public-domain",
                "redistributable": True,
                "client_scope": "open",
            },
        }
    )
    return MapConfig(default="osm-local", providers=[provider, proxied]), pmtiles_path


@pytest.fixture
def client_and_path(tmp_path: Path) -> tuple[TestClient, Path]:
    config, pmtiles_path = _config_for(tmp_path)
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_map_config] = lambda: config
    test_client = TestClient(app)
    try:
        yield test_client, pmtiles_path
    finally:
        app.dependency_overrides.clear()


def test_serves_the_file_when_it_has_been_built(client_and_path: tuple[TestClient, Path]) -> None:
    client, pmtiles_path = client_and_path
    pmtiles_path.write_bytes(b"PMTiles fixture bytes")

    response = client.get("/v1/map/local-source/osm-local")

    assert response.status_code == 200
    assert response.content == b"PMTiles fixture bytes"
    assert response.headers["accept-ranges"] == "bytes"


def test_answers_a_range_request_the_pmtiles_reader_depends_on(
    client_and_path: tuple[TestClient, Path],
) -> None:
    client, pmtiles_path = client_and_path
    pmtiles_path.write_bytes(b"0123456789")

    response = client.get("/v1/map/local-source/osm-local", headers={"Range": "bytes=2-4"})

    assert response.status_code == 206
    assert response.content == b"234"


def test_404s_with_a_named_reason_when_the_file_has_not_been_built(
    client_and_path: tuple[TestClient, Path],
) -> None:
    client, pmtiles_path = client_and_path
    assert not pmtiles_path.exists()

    response = client.get("/v1/map/local-source/osm-local")

    assert response.status_code == 404
    assert "basemap not built" in response.json()["detail"]


def test_404s_for_an_unknown_provider(client_and_path: tuple[TestClient, Path]) -> None:
    client, _ = client_and_path

    response = client.get("/v1/map/local-source/does-not-exist")

    assert response.status_code == 404


def test_404s_for_a_provider_with_no_file_source(client_and_path: tuple[TestClient, Path]) -> None:
    client, _ = client_and_path

    response = client.get("/v1/map/local-source/usgs-national-map")

    assert response.status_code == 404


def test_public_view_rewrites_a_file_source_to_this_route(tmp_path: Path) -> None:
    from services.api.mapconfig_loader import public_view

    provider = MapProvider.model_validate(
        {
            "id": "osm-local",
            "label": "OpenStreetMap",
            "kind": "vector",
            "source": f"file://{tmp_path / 'osm-local.pmtiles'}",
            "attribution": "© OpenStreetMap contributors",
            "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
        }
    )

    view = public_view(provider)

    assert view.source == "/v1/map/local-source/osm-local"
