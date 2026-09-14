"""Synthetic Location-import fixtures for CRS reprojection —
`00_ARCHITECTURE.md` §1.2.2, ADR-017. Three real projections, each with
real place coordinates expressed in that projection's own units, so a
reprojection bug (wrong zone, wrong axis order, wrong false easting) shows
up as a wrong place rather than a plausible-looking wrong number:

- EPSG:27700 — OSGB36 British National Grid (UK authoritative data).
- EPSG:32139 — NAD83 Texas Central State Plane, US survey feet.
- EPSG:2227 — NAD83 California Zone III State Plane, US survey feet.

Seeded and deterministic (`CLAUDE.md` rule 9) — the random component only
varies which reference point is listed first, never the coordinate pairs
themselves, since those are real published grid references and must not
drift.
"""

from __future__ import annotations

import random

#: (place_id, easting, northing) — real OS National Grid references.
_BRITISH_NATIONAL_GRID = (
    ("uprn-100012345", "532106", "181020"),  # Trafalgar Square, London
    ("uprn-100012346", "525745", "180454"),  # Big Ben / Westminster
    ("uprn-100012347", "545938", "184025"),  # Stratford, London
)

#: (place_id, easting, northing) — NAD83 Texas Central (EPSG:32139), US survey feet.
_TEXAS_CENTRAL = (
    ("gnis-1331235", "949218.05", "3069475.07"),  # Austin, TX (Texas State Capitol area)
    ("gnis-1331236", "952000.00", "3072500.00"),  # North Austin
)

#: (place_id, easting, northing) — NAD83 California Zone III (EPSG:2227), US survey feet.
_CALIFORNIA_ZONE_III = (
    ("gnis-277411", "6277390.19", "2399898.19"),  # Sacramento, CA (State Capitol area)
    ("gnis-277412", "6281000.00", "2403000.00"),  # North Sacramento
)

#: (place_id, bare grid reference string) — the same three London points as
#: `_BRITISH_NATIONAL_GRID`, quoted the way a UK source document actually
#: would: `01_DOMAIN_MODEL.md` §7's `grid_ref` adapter, not an
#: easting/northing pair. Digits derived by truncating the easting/northing
#: above to whole metres, so the two fixtures describe the same places.
_BRITISH_NATIONAL_GRID_REFS = (
    ("uprn-100012345", "TQ 32106 81020"),
    ("uprn-100012346", "TQ2574580454"),
    ("uprn-100012347", "tq 45938 84025"),
)


def _rows(points: tuple[tuple[str, str, str], ...], *, seed: int) -> list[dict[str, str]]:
    rng = random.Random(seed)
    ordered = list(points)
    rng.shuffle(ordered)
    return [
        {"place_id": place_id, "easting": easting, "northing": northing}
        for place_id, easting, northing in ordered
    ]


def generate_bng_rows(seed: int = 42) -> list[dict[str, str]]:
    return _rows(_BRITISH_NATIONAL_GRID, seed=seed)


def generate_texas_central_rows(seed: int = 42) -> list[dict[str, str]]:
    return _rows(_TEXAS_CENTRAL, seed=seed)


def generate_california_zone_iii_rows(seed: int = 42) -> list[dict[str, str]]:
    return _rows(_CALIFORNIA_ZONE_III, seed=seed)


def generate_bng_grid_ref_rows(seed: int = 42) -> list[dict[str, str]]:
    rng = random.Random(seed)
    ordered = list(_BRITISH_NATIONAL_GRID_REFS)
    rng.shuffle(ordered)
    return [{"place_id": place_id, "grid_ref": ref} for place_id, ref in ordered]
