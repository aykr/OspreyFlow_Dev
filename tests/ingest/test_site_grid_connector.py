"""The site-grid connector — `docs/00_ARCHITECTURE.md` §1.2's "Geospatial
reference data as entities" table, `08_ACCEPTANCE_SCENARIOS.md` A1.
`packages/geo/bilinear.py`'s own maths is exercised exhaustively in
`tests/geo/test_bilinear.py`; this only checks the row shape this connector
layers on top (`site_ref` naming, string coordinates for the recipe
engine)."""

from __future__ import annotations

import pytest
from services.ingest.connectors.geo.site_grid import site_grid_rows

from geo.bilinear import ControlPoint

_SQUARE = (
    ControlPoint(px=0, py=0, lon=-1.0, lat=1.0),
    ControlPoint(px=100, py=0, lon=1.0, lat=1.0),
    ControlPoint(px=100, py=100, lon=1.0, lat=-1.0),
    ControlPoint(px=0, py=100, lon=-1.0, lat=-1.0),
)


def test_one_row_per_grid_cell() -> None:
    rows = list(site_grid_rows(site_id="site-1", control_points=_SQUARE, rows=2, cols=2))
    assert len(rows) == 4


def test_site_ref_names_the_site_and_the_cells_position() -> None:
    rows = list(site_grid_rows(site_id="site-1", control_points=_SQUARE, rows=2, cols=2))
    refs = {r["site_ref"] for r in rows}
    assert refs == {
        "site-1-r0-c0",
        "site-1-r0-c1",
        "site-1-r1-c0",
        "site-1-r1-c1",
    }


def test_rows_carry_string_coordinates_for_the_recipe_engine() -> None:
    rows = list(site_grid_rows(site_id="site-1", control_points=_SQUARE, rows=2, cols=2))
    top_left_cell = next(r for r in rows if r["site_ref"] == "site-1-r0-c0")
    assert isinstance(top_left_cell["lon"], str)
    assert isinstance(top_left_cell["lat"], str)
    # Cell (0, 0) of a 2x2 grid over this square is centred a quarter of
    # the way in from the TL corner (-1, 1).
    assert float(top_left_cell["lon"]) == pytest.approx(-0.5)
    assert float(top_left_cell["lat"]) == pytest.approx(0.5)
