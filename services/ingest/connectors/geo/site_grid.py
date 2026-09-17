"""The site-grid connector — `docs/00_ARCHITECTURE.md` §1.2's "Geospatial
reference data as entities" table ("Site plans... GeoTIFF/image + control
points... Site grid cells as `Location`... The HMP case"),
`08_ACCEPTANCE_SCENARIOS.md` A1.

Turns a calibrated site (`services/api/sites.py`'s four control points plus
a grid row/column count) into the same `Iterable[Mapping[str, str]]` row
shape every other connector under `services/ingest/connectors/` produces,
so `site_grid_recipe.yaml` maps them to `Location` entities through the
existing recipe engine exactly the way `osm.py`'s rows do. The bilinear
maths itself lives in `packages/geo/bilinear.py`, shared with the
frontend's grid preview — this module's only job is turning `GridCell`s
into row dicts and naming each cell's `site_ref`.
"""

from __future__ import annotations

from collections.abc import Iterator

from geo.bilinear import ControlQuad, compute_grid_cells


def site_grid_rows(
    *, site_id: str, control_points: ControlQuad, rows: int, cols: int
) -> Iterator[dict[str, str]]:
    """One row per grid cell. `site_ref` is `<site_id>-r<row>-c<col>`
    (zero-based) — `packages/ontology/default.yaml`'s v8 changelog note
    names `Location.site_ref` as "a yard, a wing, a cell, eventually a
    site-grid cell". `name` is a human-readable label, not an identifier;
    `match_on: site_ref` in the recipe is what makes redrawing the grid
    idempotent rather than creating duplicate cells."""
    for cell in compute_grid_cells(control_points, rows=rows, cols=cols):
        yield {
            "site_ref": f"{site_id}-r{cell.row}-c{cell.col}",
            "name": f"Grid cell ({cell.row}, {cell.col})",
            "lon": repr(cell.centroid.lon),
            "lat": repr(cell.centroid.lat),
        }
