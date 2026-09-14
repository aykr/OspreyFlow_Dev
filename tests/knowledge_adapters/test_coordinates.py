"""Golden tests for `coordinate_lon`/`coordinate_lat` — `01_DOMAIN_MODEL.md`
§7, `00_ARCHITECTURE.md` §1.2.2, ADR-017. Fixtures cover EPSG:27700 (OSGB36
British National Grid) and two NAD83 State Plane zones from different
states, per the Phase 2 constraint that reprojection be tested against
both countries' authoritative projections, not just one.
"""

from __future__ import annotations

import pytest

from knowledge_adapters.coordinates import coordinate_lat, coordinate_lon
from knowledge_adapters.errors import NormalisationError

# OS National Grid reference near central London.
_BNG = ("532106", "181020")
# NAD83 Texas Central State Plane (EPSG:32139, US survey feet) — Austin, TX.
_TEXAS_CENTRAL = ("949218.05", "3069475.07")
# NAD83 California Zone III State Plane (EPSG:2227, US survey feet) — Sacramento, CA.
_CALIFORNIA_III = ("6277390.19", "2399898.19")


def test_british_national_grid_reprojects_to_wgs84_london() -> None:
    lon = coordinate_lon(_BNG, source_crs="EPSG:27700")
    lat = coordinate_lat(_BNG, source_crs="EPSG:27700")

    assert lon == pytest.approx(-0.0976, abs=1e-3)
    assert lat == pytest.approx(51.5127, abs=1e-3)


def test_texas_central_state_plane_reprojects_to_wgs84_austin() -> None:
    lon = coordinate_lon(_TEXAS_CENTRAL, source_crs="EPSG:32139")
    lat = coordinate_lat(_TEXAS_CENTRAL, source_crs="EPSG:32139")

    assert lon == pytest.approx(-97.7431, abs=1e-3)
    assert lat == pytest.approx(30.2672, abs=1e-3)


def test_california_zone_iii_state_plane_reprojects_to_wgs84_sacramento() -> None:
    lon = coordinate_lon(_CALIFORNIA_III, source_crs="EPSG:2227")
    lat = coordinate_lat(_CALIFORNIA_III, source_crs="EPSG:2227")

    assert lon == pytest.approx(-121.4944, abs=1e-3)
    assert lat == pytest.approx(38.5816, abs=1e-3)


def test_the_two_us_state_plane_zones_do_not_share_a_projection() -> None:
    """A regression this specific: reprojecting Sacramento's easting/northing
    as if it were Texas Central (or vice versa) must not coincidentally
    land in-bounds and pass silently — the zone genuinely matters, not just
    "NAD83" as a family name."""
    wrong_lon = coordinate_lon(_CALIFORNIA_III, source_crs="EPSG:32139")
    wrong_lat = coordinate_lat(_CALIFORNIA_III, source_crs="EPSG:32139")

    assert wrong_lon != pytest.approx(-121.4944, abs=1.0)
    assert wrong_lat != pytest.approx(38.5816, abs=1.0)


def test_undeclared_source_crs_is_rejected_not_guessed() -> None:
    with pytest.raises(NormalisationError, match="ambiguous coordinate reference system"):
        coordinate_lon(_BNG, source_crs=None)


def test_non_numeric_coordinate_is_rejected() -> None:
    with pytest.raises(NormalisationError, match="not a numeric coordinate pair"):
        coordinate_lon(("not-a-number", "181020"), source_crs="EPSG:27700")


def test_unrecognised_crs_code_is_rejected_not_silently_passed_through() -> None:
    with pytest.raises(NormalisationError, match="unrecognised coordinate reference system"):
        coordinate_lon(_BNG, source_crs="EPSG:9999999")


def test_reprojecting_with_the_wrong_countrys_crs_is_rejected_when_out_of_bounds() -> None:
    """British National Grid eastings/northings, misdeclared as if they were
    already WGS84 degrees, produce a result far outside valid longitude —
    caught as a bounds violation rather than silently stored."""
    with pytest.raises(NormalisationError, match="outside WGS84 bounds"):
        coordinate_lon(("532106", "181020"), source_crs="EPSG:4326")
