"""`GET /v1/map/providers` route wiring — `docs/02_GLASS_FRONTEND.md` §3.5's
layer control, served from `osprey.yaml`'s loaded registry rather than
duplicated client-side. Same style as `test_ontology_route.py`: fakes
behind `app.dependency_overrides`, proving only the wiring — the sanitised
`public_view()` projection itself is `test_mapconfig_loader.py`'s job.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_map_config, get_principal
from services.api.mapconfig_loader import load_map_config

from schemas.domain import Principal

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")

FIXTURE_CONFIG = """
map:
  default: osm-local
  providers:
    - id: osm-local
      label: "OpenStreetMap"
      kind: vector
      source: file:///data/tiles/gb-osm.pmtiles
      style: bundled:osprey-dark
      attribution: "© OpenStreetMap contributors"
      licence: {id: ODbL, redistributable: true, client_scope: open}
    - id: os-ngd
      label: "OS NGD"
      kind: vector
      source: "os-datahub://ngd/tiles"
      credential: env:OS_DATAHUB_API_KEY
      proxy: required
      attribution: "Contains OS data (c) Crown copyright"
      licence: {id: PSGA, redistributable: false, client_scope: per-deployment}
"""


@pytest.fixture
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    path = tmp_path_factory.mktemp("osprey") / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG)
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_map_config] = lambda: load_map_config(path)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_returns_every_declared_provider_and_the_default_id(client: TestClient) -> None:
    response = client.get("/v1/map/providers")

    assert response.status_code == 200
    body = response.json()
    assert body["default"] == "osm-local"
    assert {p["id"] for p in body["providers"]} == {"osm-local", "os-ngd"}


def test_never_discloses_a_credential_or_a_proxied_source(client: TestClient) -> None:
    response = client.get("/v1/map/providers")

    providers = response.json()["providers"]
    assert all("credential" not in p for p in providers)
    local = next(p for p in providers if p["id"] == "osm-local")
    proxied = next(p for p in providers if p["id"] == "os-ngd")
    assert local["source"] == "file:///data/tiles/gb-osm.pmtiles"
    assert proxied["source"] is None  # never the raw os-datahub:// source
    assert local["client_scope"] == "open"
    assert proxied["client_scope"] == "per-deployment"


def test_requires_authentication(client: TestClient) -> None:
    app.dependency_overrides.pop(get_principal)

    response = client.get("/v1/map/providers")

    assert response.status_code in (401, 403)
