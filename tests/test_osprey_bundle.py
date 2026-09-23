"""`scripts/osprey_bundle.py` — `docs/00_ARCHITECTURE.md` §1.2's "the
bundle step refuses to package tiles or gazetteers whose profile says
`redistributable: false`, and names them". Proves the refusal against a fixture config that
deliberately violates it — the same "prove the gate with a fixture that
intentionally violates it" pattern `tests/licence_check/
test_gpl_rejection.py` already established for package licences (a
different concern, reused only as a pattern, no shared code).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.osprey_bundle import (
    BundleResult,
    NonRedistributableProviderError,
    bundle_map_providers,
)
from services.api.mapconfig_loader import load_map_config

FIXTURE_ALL_OPEN = """
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
    - id: os-open-zoomstack-local
      label: "OS Open Zoomstack"
      kind: vector
      source: file:///data/tiles/os-open-zoomstack.pmtiles
      style: bundled:osprey-dark
      attribution: "Contains OS data (c) Crown copyright and database right"
      licence: {id: OGL-UK-3.0, redistributable: true, client_scope: open}
"""

FIXTURE_ONE_NON_REDISTRIBUTABLE = """
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


def test_bundles_every_provider_when_all_are_redistributable(tmp_path: Path) -> None:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_ALL_OPEN)
    config = load_map_config(path)

    result = bundle_map_providers(config)

    assert isinstance(result, BundleResult)
    assert set(result.bundled_provider_ids) == {"osm-local", "os-open-zoomstack-local"}


def test_refuses_the_whole_bundle_and_names_the_non_redistributable_provider(
    tmp_path: Path,
) -> None:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_ONE_NON_REDISTRIBUTABLE)
    config = load_map_config(path)

    with pytest.raises(NonRedistributableProviderError) as exc_info:
        bundle_map_providers(config)

    assert exc_info.value.refused_provider_ids == ("os-ngd",)
    assert "os-ngd" in str(exc_info.value)
