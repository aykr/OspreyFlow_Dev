"""Well-known binary for a polygon, packed by hand — round 13cf.

The only writer is the site-grid route (owner ruling R9 (a): a cell is a `POLYGON`). A shapely
dependency for one ring of four corners would be the heavier choice. The format is small and
fixed: little-endian byte order, geometry type 3 (Polygon), one ring, the ring's points as
`(x, y)` doubles, closed by repeating the first point. `tests/geo/test_wkb.py` checks the bytes
against DuckDB's own `ST_GeomFromText` → `ST_AsWKB` for the same polygon.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence


def polygon_wkb(ring: Sequence[tuple[float, float]]) -> bytes:
    """`ring` is `(lon, lat)` corners, unclosed. It is closed here."""
    if len(ring) < 3:
        raise ValueError(f"a polygon ring needs at least three corners, got {len(ring)}")
    closed = [*ring, ring[0]]
    body = b"".join(struct.pack("<dd", x, y) for x, y in closed)
    return struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(closed)) + body


def ring_centroid(ring: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """The derived point for a cell (R9 (b)): the mean of its four corners. A bilinear grid cell
    is a convex quadrilateral, so this point lies inside it. It is for drawing only, never for
    containment, which uses the polygon itself."""
    xs, ys = zip(*ring, strict=True)
    return sum(xs) / len(xs), sum(ys) / len(ys)
