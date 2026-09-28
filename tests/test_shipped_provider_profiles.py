"""The shipped `providers/` profiles — `spec/00_ARCHITECTURE.md` §1.2's
"Profiles to ship in `providers/`, each with a Verify fixture", scoped to
one UK and one US profile.

**What "Verify fixture" means at this checkpoint.** A profile's own
`zoom`/`projection`/`attribution` are typed in by hand when the profile is
authored — this test proves they were typed in *correctly*, by cross-
checking them against a canned capabilities/metadata response for the real
service (`tests/fixtures/provider_profiles/*.json`), not by calling the
service live (rule 9: fixtures synthetic and in-repo). This is narrower
than `verify_map` (Checkpoint 3c's post-registration, any-active-provider,
contrast-floor-included check) — it only proves a shipped profile file
itself is well-formed against what its real service is known to declare.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from services.api.provider_profile_loader import load_provider_profile

PROVIDERS_DIR = Path(__file__).resolve().parents[1] / "providers"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "provider_profiles"


def _capabilities(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text())


def test_os_open_zoomstack_profile_loads_and_is_open_and_redistributable() -> None:
    profile = load_provider_profile(PROVIDERS_DIR / "os-open-zoomstack.yaml")
    assert profile.id == "os-open-zoomstack"
    assert profile.licence.redistributable is True
    assert profile.licence.client_scope == "open"


def test_os_open_zoomstack_matches_its_known_capabilities_fixture() -> None:
    profile = load_provider_profile(PROVIDERS_DIR / "os-open-zoomstack.yaml")
    capabilities = _capabilities("os_open_zoomstack_capabilities.json")

    assert profile.zoom.min == capabilities["minzoom"]
    assert profile.zoom.max == capabilities["maxzoom"]
    assert profile.attribution == capabilities["attribution"]


def test_usgs_national_map_profile_loads_and_is_open_and_redistributable() -> None:
    profile = load_provider_profile(PROVIDERS_DIR / "usgs-national-map.yaml")
    assert profile.id == "usgs-national-map"
    assert profile.licence.redistributable is True
    assert profile.licence.client_scope == "open"


def test_usgs_national_map_matches_its_known_capabilities_fixture() -> None:
    profile = load_provider_profile(PROVIDERS_DIR / "usgs-national-map.yaml")
    capabilities = _capabilities("usgs_national_map_capabilities.json")
    tile_matrix_set = capabilities["tile_matrix_set"]
    assert isinstance(tile_matrix_set, dict)

    assert profile.projection == tile_matrix_set["projection"]
    assert profile.zoom.min == tile_matrix_set["min_zoom"]
    assert profile.zoom.max == tile_matrix_set["max_zoom"]
    assert profile.attribution == capabilities["attribution"]
    # Every `variables.layer` option this profile offers must be a real
    # layer the service actually exposes — a typo here would silently
    # offer a choice that 404s at render time.
    assert set(profile.variables["layer"].options) == set(capabilities["layers"])


@pytest.mark.parametrize(
    "filename", ["os-open-zoomstack.yaml", "usgs-national-map.yaml"]
)
def test_every_shipped_profile_has_a_capabilities_fixture(filename: str) -> None:
    profile = load_provider_profile(PROVIDERS_DIR / filename)
    fixture_path = FIXTURES_DIR / f"{profile.id.replace('-', '_')}_capabilities.json"
    assert fixture_path.is_file(), f"missing verify fixture for shipped profile {profile.id!r}"
