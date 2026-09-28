"""Slippy-map tile math — `spec/05_DEPLOYMENT.md` §2.2's "Prefetch area of
operations", a disclosed known-gaps closure. Nothing
in this repo converts a lon/lat bounding box to a `{z}/{x}/{y}` tile range before this;
kept pure and dependency-free (no `mercantile`) since the formula is small
and this is the only place it is needed.

Web Mercator only (`services/api/tier4_registration.py`'s own
`SUPPORTED_CRS` — EPSG:3857/EPSG:4326 — is what every tile provider this
platform proxies actually uses); a bounding box crossing the antimeridian
(`min_lon > max_lon`) is refused rather than silently computing a wrong,
inverted range — real, separate work if a deployment ever needs it, not
assumed away.
"""

from __future__ import annotations

import math
from collections.abc import Iterator


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """The standard OSM/Web-Mercator slippy-map tile containing a point,
    at a given zoom level."""
    lat = max(min(lat, 85.05112878), -85.05112878)  # Web Mercator's own lat clamp
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (max(0, min(n - 1, x)), max(0, min(n - 1, y)))


def tile_range_for_bbox(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float, zoom: int
) -> tuple[int, int, int, int]:
    """`(x_min, x_max, y_min, y_max)`, inclusive, covering the bounding box
    at `zoom`. Latitude increases northward but tile `y` increases
    southward, so the tile for `max_lat` is the smaller `y`."""
    if min_lon > max_lon:
        raise ValueError(
            f"bounding box crosses the antimeridian (min_lon={min_lon} > max_lon={max_lon}) "
            "— not supported yet"
        )
    x_at_min_lon, y_at_max_lat = lonlat_to_tile(min_lon, max_lat, zoom)
    x_at_max_lon, y_at_min_lat = lonlat_to_tile(max_lon, min_lat, zoom)
    return (x_at_min_lon, x_at_max_lon, y_at_max_lat, y_at_min_lat)


def tiles_in_range(x_min: int, x_max: int, y_min: int, y_max: int) -> Iterator[tuple[int, int]]:
    """Every `(x, y)` pair in the inclusive range `tile_range_for_bbox`
    returns, in a stable (row-major) order — deterministic for tests and
    for a prefetch job's own progress reporting."""
    for y in range(y_min, y_max + 1):
        for x in range(x_min, x_max + 1):
            yield (x, y)
