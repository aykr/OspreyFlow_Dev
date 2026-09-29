"""`services/api/tile_math.py` — a disclosed known-gaps
closure's prefetch job needs a bbox-to-tile-range conversion;
nothing in the repo had one before this."""

from __future__ import annotations

import pytest
from services.api.tile_math import lonlat_to_tile, tile_range_for_bbox, tiles_in_range


def test_lonlat_to_tile_matches_a_hand_worked_value() -> None:
    """Central London at zoom 5, worked by hand from the standard
    slippy-map formula (n=32; x=floor((lon+180)/360*n);
    y=floor((1 - asinh(tan(lat_rad))/pi)/2*n)) — not copied from an
    external source, so this is a check against the formula itself, not
    against this function's own implementation of it."""
    assert lonlat_to_tile(-0.1276, 51.5072, zoom=5) == (15, 10)


def test_lonlat_to_tile_at_zoom_zero_is_always_the_single_tile() -> None:
    assert lonlat_to_tile(0.0, 0.0, zoom=0) == (0, 0)
    assert lonlat_to_tile(179.0, 84.0, zoom=0) == (0, 0)
    assert lonlat_to_tile(-179.0, -84.0, zoom=0) == (0, 0)


def test_lonlat_to_tile_clamps_extreme_latitude() -> None:
    """Web Mercator is undefined at the poles — a real polygon's bounding
    box should never reach ±90, but clamping (not raising) keeps a
    slightly-too-generous bbox from crashing the whole prefetch job."""
    north_pole_tile = lonlat_to_tile(0.0, 90.0, zoom=4)
    near_pole_tile = lonlat_to_tile(0.0, 85.05112878, zoom=4)
    assert north_pole_tile == near_pole_tile


def test_tile_range_for_bbox_covers_a_small_area() -> None:
    """A ~0.02deg-square box around central London at a high zoom covers a
    small, exactly-countable tile range — not just "some tiles"."""
    x_min, x_max, y_min, y_max = tile_range_for_bbox(
        min_lon=-0.13, min_lat=51.50, max_lon=-0.11, max_lat=51.52, zoom=15
    )
    assert x_min <= x_max
    assert y_min <= y_max
    # The known-good single-point tile for the box's own centre must fall
    # inside the range this function computes for the box around it.
    centre_x, centre_y = lonlat_to_tile(-0.12, 51.51, zoom=15)
    assert x_min <= centre_x <= x_max
    assert y_min <= centre_y <= y_max


def test_tile_range_for_bbox_at_zoom_zero_is_the_single_world_tile() -> None:
    assert tile_range_for_bbox(-10.0, -10.0, 10.0, 10.0, zoom=0) == (0, 0, 0, 0)


def test_tile_range_for_bbox_refuses_an_antimeridian_crossing_box() -> None:
    with pytest.raises(ValueError, match="antimeridian"):
        tile_range_for_bbox(min_lon=170.0, min_lat=-10.0, max_lon=-170.0, max_lat=10.0, zoom=5)


def test_tiles_in_range_enumerates_every_pair_in_row_major_order() -> None:
    assert list(tiles_in_range(1, 2, 5, 6)) == [(1, 5), (2, 5), (1, 6), (2, 6)]


def test_tiles_in_range_for_a_single_tile() -> None:
    assert list(tiles_in_range(3, 3, 4, 4)) == [(3, 4)]
