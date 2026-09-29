"""`packages/geo/bilinear.py` — `08_ACCEPTANCE_SCENARIOS.md` A1's site
grid. Pure maths, no store of any kind needed."""

from __future__ import annotations

import pytest

from geo.bilinear import ControlPoint, compute_grid_cells

# An axis-aligned square, world corners at (+/-1, +/-1) — makes an evenly
# spaced grid's expected coordinates simple arithmetic to state and check.
_SQUARE = (
    ControlPoint(px=0, py=0, lon=-1.0, lat=1.0),  # TL
    ControlPoint(px=100, py=0, lon=1.0, lat=1.0),  # TR
    ControlPoint(px=100, py=100, lon=1.0, lat=-1.0),  # BR
    ControlPoint(px=0, py=100, lon=-1.0, lat=-1.0),  # BL
)

# A rotated, non-rectangular quad — the same winding order (TL, TR, BR,
# BL) but no axis alignment, so a bug that only happens to work for
# rectangles (e.g. swapping u/v) would still be caught.
_SKEWED = (
    ControlPoint(px=0, py=0, lon=0.0, lat=2.0),  # TL
    ControlPoint(px=100, py=10, lon=3.0, lat=2.5),  # TR
    ControlPoint(px=90, py=100, lon=2.5, lat=-1.0),  # BR
    ControlPoint(px=-10, py=90, lon=-0.5, lat=-0.5),  # BL
)


def test_a_square_control_quad_produces_an_evenly_spaced_grid() -> None:
    cells = compute_grid_cells(_SQUARE, rows=10, cols=10)
    assert len(cells) == 100

    by_rc = {(c.row, c.col): c for c in cells}
    first, last = by_rc[(0, 0)], by_rc[(9, 9)]

    # First cell's centroid is half a cell-width in from the TL corner.
    assert first.centroid.lon == pytest.approx(-1.0 + 0.1)
    assert first.centroid.lat == pytest.approx(1.0 - 0.1)
    # Last cell's centroid is symmetric, half a cell-width in from BR.
    assert last.centroid.lon == pytest.approx(1.0 - 0.1)
    assert last.centroid.lat == pytest.approx(-1.0 + 0.1)


def test_the_grids_outer_corners_match_the_control_points_exactly() -> None:
    for control_points in (_SQUARE, _SKEWED):
        cells = compute_grid_cells(control_points, rows=10, cols=10)
        by_rc = {(c.row, c.col): c for c in cells}
        tl, tr, br, bl = control_points

        top_left_corner = by_rc[(0, 0)].corners[0]
        top_right_corner = by_rc[(0, 9)].corners[1]
        bottom_right_corner = by_rc[(9, 9)].corners[2]
        bottom_left_corner = by_rc[(9, 0)].corners[3]

        assert top_left_corner.lon == pytest.approx(tl.lon)
        assert top_left_corner.lat == pytest.approx(tl.lat)
        assert top_right_corner.lon == pytest.approx(tr.lon)
        assert top_right_corner.lat == pytest.approx(tr.lat)
        assert bottom_right_corner.lon == pytest.approx(br.lon)
        assert bottom_right_corner.lat == pytest.approx(br.lat)
        assert bottom_left_corner.lon == pytest.approx(bl.lon)
        assert bottom_left_corner.lat == pytest.approx(bl.lat)


def test_adjacent_cells_share_corners_exactly_with_no_gap_or_overlap() -> None:
    cells = compute_grid_cells(_SKEWED, rows=5, cols=5)
    by_rc = {(c.row, c.col): c for c in cells}

    # (r, c)'s right edge is (r, c+1)'s left edge.
    left = by_rc[(2, 2)]
    right = by_rc[(2, 3)]
    assert left.corners[1] == right.corners[0]  # TR == TL
    assert left.corners[2] == right.corners[3]  # BR == BL

    # (r, c)'s bottom edge is (r+1, c)'s top edge.
    top = by_rc[(2, 2)]
    bottom = by_rc[(3, 2)]
    assert top.corners[3] == bottom.corners[0]  # BL == TL
    assert top.corners[2] == bottom.corners[1]  # BR == TR


def test_a_single_cell_grid_spans_the_whole_quad() -> None:
    cells = compute_grid_cells(_SKEWED, rows=1, cols=1)
    assert len(cells) == 1
    cell = cells[0]
    tl, tr, br, bl = _SKEWED
    assert cell.corners[0].lon == pytest.approx(tl.lon)
    assert cell.corners[0].lat == pytest.approx(tl.lat)
    assert cell.corners[1].lon == pytest.approx(tr.lon)
    assert cell.corners[2].lon == pytest.approx(br.lon)
    assert cell.corners[3].lon == pytest.approx(bl.lon)


@pytest.mark.parametrize("rows,cols", [(0, 10), (10, 0), (-1, 5)])
def test_a_non_positive_row_or_column_count_is_rejected(rows: int, cols: int) -> None:
    with pytest.raises(ValueError, match="rows/cols"):
        compute_grid_cells(_SQUARE, rows=rows, cols=cols)
