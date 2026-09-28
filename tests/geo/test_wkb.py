"""`packages/geo/wkb.py` against DuckDB's own encoder — round 13cf."""

from __future__ import annotations

import duckdb
import pytest

from geo.wkb import polygon_wkb, ring_centroid

_RING = [(-1.836, 52.409), (-1.8355, 52.409), (-1.8355, 52.40875), (-1.836, 52.40875)]


def test_polygon_wkb_matches_duckdbs_own_encoding_of_the_same_polygon() -> None:
    con = duckdb.connect(":memory:")
    try:
        con.install_extension("spatial")
        con.load_extension("spatial")
        wkt = "POLYGON((" + ", ".join(f"{x} {y}" for x, y in [*_RING, _RING[0]]) + "))"
        expected = con.execute("SELECT ST_AsWKB(ST_GeomFromText(?))", [wkt]).fetchone()[0]
        # And it round-trips: DuckDB reads the hand-packed bytes as the same polygon.
        same = con.execute(
            "SELECT ST_Equals(ST_GeomFromWKB(?), ST_GeomFromText(?))", [polygon_wkb(_RING), wkt]
        ).fetchone()[0]
    finally:
        con.close()
    assert polygon_wkb(_RING) == bytes(expected)
    assert same is True


def test_polygon_wkb_refuses_a_ring_too_short_to_be_a_polygon() -> None:
    with pytest.raises(ValueError, match="at least three"):
        polygon_wkb(_RING[:2])


def test_ring_centroid_is_the_mean_of_the_corners() -> None:
    assert ring_centroid(_RING) == pytest.approx((-1.83575, 52.408875))
