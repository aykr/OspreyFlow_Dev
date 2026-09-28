"""`services/api/mapconfig_loader.py` — `spec/00_ARCHITECTURE.md` §1.2."""

from __future__ import annotations

from pathlib import Path

from services.api.mapconfig_loader import load_map_config, public_view

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_load_map_config_reads_the_map_section_of_an_osprey_yaml(tmp_path: Path) -> None:
    path = tmp_path / "osprey.yaml"
    path.write_text(
        """
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
"""
    )
    config = load_map_config(path)
    assert config.default == "osm-local"
    assert config.providers[0].id == "osm-local"


def test_public_view_exposes_a_local_source_but_never_a_credential(tmp_path: Path) -> None:
    path = tmp_path / "osprey.yaml"
    path.write_text(
        """
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
    )
    config = load_map_config(path)
    local, proxied = config.providers

    local_view = public_view(local)
    # Never the raw `file://` path — a browser cannot fetch it at all (Stage 3a's own rehearsal
    # finding, 23 September 2026). Rewritten to the Conduit's own local-source route instead;
    # `tests/services/api/test_map_local_source_route.py` proves that route serves the bytes.
    assert local_view.source == "/v1/map/local-source/osm-local"
    assert local_view.client_scope == "open"
    assert not hasattr(local_view, "credential")

    proxied_view = public_view(proxied)
    assert proxied_view.source is None  # never the raw os-datahub:// source
    assert proxied_view.client_scope == "per-deployment"
    assert not hasattr(proxied_view, "credential")
