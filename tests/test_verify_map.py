"""`scripts/verify_map.py` — `docs/00_ARCHITECTURE.md` §1.2.1's Verify
check, `docs/07_BUILD_PLAN.md` Phase 5 Checkpoint 3c. The one
network-dependent stage (`check_crs_and_zoom`'s tier-4 capabilities fetch)
is injected out, the same discipline `test_build_local_basemap.py`
already established for its own network-dependent stages.
"""

from __future__ import annotations

from scripts.verify_map import check_attribution, check_crs_and_zoom, verify_map
from services.api.tier4_registration import DiscoveredCapabilities, UnsupportedProjectionError

from schemas.mapconfig import MapConfig, MapProvider


def _vector_provider(**overrides: object) -> MapProvider:
    base: dict[str, object] = {
        "id": "osm-local",
        "label": "OpenStreetMap",
        "kind": "vector",
        "source": "file:///data/tiles/osm-local.pmtiles",
        "attribution": "© OpenStreetMap contributors",
        "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
    }
    base.update(overrides)
    return MapProvider.model_validate(base)


def _tier4_provider(**overrides: object) -> MapProvider:
    base: dict[str, object] = {
        "id": "usgs-national-map",
        "label": "USGS The National Map",
        "kind": "raster",
        "service": "wmts",
        "endpoint": "https://basemap.nationalmap.gov/wmts",
        "proxy": "recommended",
        "attribution": "USGS The National Map",
        "licence": {"id": "usgs-public-domain", "redistributable": True, "client_scope": "open"},
    }
    base.update(overrides)
    return MapProvider.model_validate(base)


def test_check_attribution_passes_for_a_provider_with_attribution() -> None:
    assert check_attribution(_vector_provider()) is None


def test_check_attribution_fails_for_a_blank_attribution() -> None:
    issue = check_attribution(_vector_provider(attribution=""))
    assert issue is not None
    assert issue.check == "attribution"


async def test_check_crs_and_zoom_is_a_no_op_for_a_tier_1_provider() -> None:
    assert await check_crs_and_zoom(_vector_provider()) is None


async def test_check_crs_and_zoom_passes_for_a_tier_4_provider_with_a_supported_crs() -> None:
    async def fake_register(endpoint: str) -> DiscoveredCapabilities:
        return DiscoveredCapabilities(
            layers=("Layer",),
            projection="EPSG:3857",
            zoom_min=0,
            zoom_max=16,
            tile_matrix_set="GoogleMapsCompatible",
            format="image/png",
            style="default",
        )

    issue = await check_crs_and_zoom(_tier4_provider(), register=fake_register)
    assert issue is None


async def test_check_crs_and_zoom_fails_for_a_tier_4_provider_with_an_unsupported_crs() -> None:
    async def fake_register(endpoint: str) -> DiscoveredCapabilities:
        raise UnsupportedProjectionError("EPSG:27700")

    issue = await check_crs_and_zoom(_tier4_provider(), register=fake_register)
    assert issue is not None
    assert issue.check == "crs"


async def test_verify_map_reports_every_issue_across_every_provider() -> None:
    async def fake_register(endpoint: str) -> DiscoveredCapabilities:
        raise UnsupportedProjectionError("EPSG:27700")

    config = MapConfig(
        default="osm-local",
        providers=[_vector_provider(attribution=""), _tier4_provider()],
    )

    report = await verify_map(config, register=fake_register)

    assert not report.passed
    assert {issue.provider_id for issue in report.issues} == {"osm-local", "usgs-national-map"}


async def test_verify_map_passes_when_every_provider_is_clean() -> None:
    async def fake_register(endpoint: str) -> DiscoveredCapabilities:
        return DiscoveredCapabilities(
            layers=("Layer",),
            projection="EPSG:3857",
            zoom_min=0,
            zoom_max=16,
            tile_matrix_set="GoogleMapsCompatible",
            format="image/png",
            style="default",
        )

    config = MapConfig(default="osm-local", providers=[_vector_provider(), _tier4_provider()])

    report = await verify_map(config, register=fake_register)

    assert report.passed
