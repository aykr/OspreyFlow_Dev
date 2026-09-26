"""`06_DECISIONS.md` ADR-049 Stage 2 §6 part B, item 2 — the Geospatial screen's own three routes.
`harness/geospatial.py`'s own docstring has the full, confirmed-by-import reason only
`register-provider` is real here: `build_local_basemap` and `verify_map` each pull in `services`/
`adapters` modules `harness/Dockerfile` does not copy into this image, so both routes always
refuse — proven below as the real, typed 501 they are, never silently skipped or stubbed as a
pass."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from harness.webapp import create_app


def _client(config_path: Path) -> TestClient:
    app = create_app(config_path=config_path)
    return TestClient(app, client=("127.0.0.1", 51000))


def test_registering_a_local_provider_writes_the_map_section(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    client = _client(config_path)

    response = client.post(
        "/api/geospatial/register-provider",
        json={
            "provider_id": "osm-local-gb",
            "label": "OpenStreetMap (GB)",
            "pmtiles_path": str(tmp_path / "gb.pmtiles"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["default"] == "osm-local-gb"
    assert body["providers"][0]["id"] == "osm-local-gb"

    on_disk = yaml.safe_load(config_path.read_text())
    assert on_disk["map"]["default"] == "osm-local-gb"


def test_registering_a_provider_never_needs_the_pmtiles_file_to_actually_exist(
    tmp_path: Path,
) -> None:
    """`register_local_provider`'s own contract (`scripts/geo_local_provider.py`): it upserts a
    config entry, it never opens the file at `pmtiles_path` — a real, if inert, capability the
    Geospatial screen can offer even with no fixture PMTiles anywhere in this tree (confirmed:
    none exists, `find . -iname "*.pmtiles"` returns nothing)."""
    config_path = tmp_path / "osprey.yaml"
    client = _client(config_path)
    response = client.post(
        "/api/geospatial/register-provider",
        json={
            "provider_id": "osm-local-gb",
            "label": "GB",
            "pmtiles_path": "/nonexistent/gb.pmtiles",
        },
    )
    assert response.status_code == 200


def test_registering_a_provider_preserves_other_sections_already_written(tmp_path: Path) -> None:
    """The same regression `tests/test_build_local_basemap.py::
    test_register_local_provider_preserves_other_top_level_keys` proves at the function level,
    proven again at the route a real Profile → Geospatial walkthrough actually takes."""
    config_path = tmp_path / "osprey.yaml"
    client = _client(config_path)
    client.put("/api/config", json={"profile": "local-lite"})

    client.post(
        "/api/geospatial/register-provider",
        json={"provider_id": "osm-local-gb", "label": "GB", "pmtiles_path": "/tmp/gb.pmtiles"},
    )

    config = client.get("/api/config").json()
    assert config["profile"] == "local-lite"
    assert "map" in config


def test_a_missing_field_is_422_not_a_500(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml")
    response = client.post("/api/geospatial/register-provider", json={"provider_id": "x"})
    assert response.status_code == 422


def test_build_basemap_refuses_with_the_real_reason(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml")
    response = client.post("/api/geospatial/build-basemap", json={})
    assert response.status_code == 501
    assert "services.ingest" in response.json()["detail"]
    assert "adapters.graph_arcadedb" in response.json()["detail"]


def test_verify_refuses_with_the_real_reason(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml")
    response = client.post("/api/geospatial/verify", json={})
    assert response.status_code == 501
    assert "services.api" in response.json()["detail"]
