"""Bilinear georeferencing across a 4-control-point quadrilateral —
`spec/00_ARCHITECTURE.md` §1.2's "Geospatial reference data as entities"
("Site plans... GeoTIFF/image + control points... Site grid cells as
`Location`"), `spec/02_GLASS_FRONTEND.md` §3.5, `08_ACCEPTANCE_SCENARIOS.md`
A1 ("place four control points, draw a 10x10 grid").

Deliberately bilinear, not a general homography/projective transform: the
same simple mapping MapLibre's own native `image` source uses to place a
4-corner raster (a `type: "image"` source's `coordinates` array), so the
rendered image and the computed grid line up under the same maths, and so
this needs no matrix-inversion dependency. Control points are assumed to be
given in a fixed winding order — top-left, top-right, bottom-right,
bottom-left — a data-contract this module relies on but cannot itself
verify from pixel content (nothing about an arbitrary uploaded photograph
lets software infer which corner is "top-left"); the calibration wizard
that collects them is what fixes this order in practice.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlPoint:
    """One correspondence the analyst placed: an image-pixel location and
    the world (WGS84 lon/lat) location it names. `px`/`py` play no part in
    this module's own interpolation (only the world corners matter for
    that) but are carried on the record because they are what the
    calibration UI actually captured, and are what places the source image
    itself as a MapLibre raster over the same four world corners."""

    px: float
    py: float
    lon: float
    lat: float


@dataclass(frozen=True)
class WorldPoint:
    lon: float
    lat: float


ControlQuad = tuple[ControlPoint, ControlPoint, ControlPoint, ControlPoint]


def _bilinear(control_points: ControlQuad, u: float, v: float) -> WorldPoint:
    """`control_points` in TL, TR, BR, BL winding order. `(u, v)` ranges
    over `[0, 1] x [0, 1]`, with `(0, 0)` = TL, `(1, 0)` = TR, `(1, 1)` =
    BR, `(0, 1)` = BL — standard bilinear interpolation across the
    quadrilateral they define, not a projective/perspective transform."""
    tl, tr, br, bl = control_points
    top_lon = tl.lon + (tr.lon - tl.lon) * u
    top_lat = tl.lat + (tr.lat - tl.lat) * u
    bottom_lon = bl.lon + (br.lon - bl.lon) * u
    bottom_lat = bl.lat + (br.lat - bl.lat) * u
    return WorldPoint(
        lon=top_lon + (bottom_lon - top_lon) * v,
        lat=top_lat + (bottom_lat - top_lat) * v,
    )


@dataclass(frozen=True)
class GridCell:
    row: int
    col: int
    #: TL, TR, BR, BL — the same winding order as `control_points`.
    corners: tuple[WorldPoint, WorldPoint, WorldPoint, WorldPoint]
    centroid: WorldPoint


def compute_grid_cells(control_points: ControlQuad, *, rows: int, cols: int) -> list[GridCell]:
    """One `GridCell` per `(row, col)`, row-major, both zero-based counting
    from the TL/TR edge: row 0 is the edge nearest `control_points[0]`
    (TL) and `control_points[1]` (TR); col 0 is the edge nearest TL and
    `control_points[3]` (BL). `08_ACCEPTANCE_SCENARIOS.md` A1's "draw a
    10x10 grid" is `rows=cols=10`."""
    if rows < 1 or cols < 1:
        raise ValueError(f"rows/cols must both be >= 1, got rows={rows} cols={cols}")
    cells: list[GridCell] = []
    for row in range(rows):
        v0, v1 = row / rows, (row + 1) / rows
        v_mid = (row + 0.5) / rows
        for col in range(cols):
            u0, u1 = col / cols, (col + 1) / cols
            u_mid = (col + 0.5) / cols
            corners = (
                _bilinear(control_points, u0, v0),
                _bilinear(control_points, u1, v0),
                _bilinear(control_points, u1, v1),
                _bilinear(control_points, u0, v1),
            )
            cells.append(
                GridCell(
                    row=row,
                    col=col,
                    corners=corners,
                    centroid=_bilinear(control_points, u_mid, v_mid),
                )
            )
    return cells
