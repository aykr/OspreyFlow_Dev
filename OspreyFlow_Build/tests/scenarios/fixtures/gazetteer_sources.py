"""Synthetic row generators for the seven remaining UK/US gazetteer
sources. Each function's
column names mirror that source's own real, published schema (not a
copy-pasted generic shape), so a wrong-field-name bug in a recipe shows up
immediately rather than passing by accident. Real, well-known place
coordinates throughout ("synthetic and in-repo" is
about the *rows*, not about inventing implausible coordinates) — reusing
`geo_locations.py`'s own already-verified British National Grid reference
points for the two BNG-sourced fixtures (OS Open Names, Code-Point Open)
rather than deriving new ones this module cannot independently check.

Seeded and deterministic — the shuffle order varies, the coordinate pairs
never do.
"""

from __future__ import annotations

import random

# --- OS Open Names (BNG, EPSG:27700) — same three London reference points
# `geo_locations.py`'s own `_BRITISH_NATIONAL_GRID` already uses. Real OS
# Open Names ids are long alphanumeric OSGB references; the shape below is
# representative, not literal. -------------------------------------------
_OS_OPEN_NAMES = (
    ("osgb4000000074219665", "Trafalgar Square", "532106", "181020"),
    ("osgb4000000074219666", "Westminster", "525745", "180454"),
    ("osgb4000000074219667", "Stratford", "545938", "184025"),
)

# --- Open UPRN (WGS84 lat/lon — OS's Open UPRN product ships both BNG and
# WGS84 columns; this fixture uses the WGS84 ones directly). -------------
_OPEN_UPRN = (
    ("100012345", "51.5079", "-0.0877"),  # near London Bridge
    ("100012346", "51.5138", "-0.0984"),  # near Liverpool Street
    ("100012347", "51.5033", "-0.1195"),  # Southwark
)

# --- Code-Point Open (BNG, EPSG:27700) — postcode-centroid gazetteer,
# same reference points as OS Open Names above (postcode centroids for
# the same three areas). --------------------------------------------------
_CODE_POINT_OPEN = (
    ("WC2N 5DN", "532106", "181020"),  # Trafalgar Square
    ("SW1A 0AA", "525745", "180454"),  # Westminster
    ("E15 1AA", "545938", "184025"),  # Stratford
)

# --- Boundary-Line — administrative areas, no single point
# (`packages/ontology/default.yaml`'s own "a jurisdiction... must be able
# to carry none" allowance) — GSS/ONS area codes are real-shaped. --------
_BOUNDARY_LINE = (
    ("E09000033", "Westminster", "London Borough"),
    ("E09000001", "City of London", "London Borough"),
    ("E09000012", "Hackney", "London Borough"),
)

# --- USGS GNIS (pipe-delimited National File format) — real feature
# coordinates around Austin, TX. ------------------------------------------
_USGS_GNIS = (
    ("1331235", "Texas State Capitol", "Capitol Building", "TX", "Travis",
     "30.274670", "-97.740370"),
    ("1331236", "Barton Springs Pool", "Spring", "TX", "Travis", "30.263610", "-97.770830"),
)

# --- Census TIGER-Line — road segments carry address *ranges*, not a
# point (`00_ARCHITECTURE.md`'s own stated caveat); this fixture supplies
# a pre-computed representative point per segment (the range midpoint) —
# the real range-to-point interpolation is out of this checkpoint's scope
# (see `services/ingest/connectors/geo/` module docstring — there isn't
# one, deliberately, for this source). ------------------------------------
_TIGER_LINE = (
    ("110435556789", "Congress Ave", "100", "198", "101", "199", "30.267500", "-97.743500"),
    ("110435556790", "6th St", "200", "298", "201", "299", "30.267000", "-97.742000"),
)

# --- National Address Database — voluntary, state-contributed
# (`00_ARCHITECTURE.md`'s own stated uneven-coverage caveat), real
# coordinates around Sacramento, CA. --------------------------------------
_NAD = (
    ("CA-SAC-0001", "1315 10th St", "Sacramento", "CA", "95814", "38.576600", "-121.493400"),
    ("CA-SAC-0002", "1300 I St", "Sacramento", "CA", "95814", "38.579500", "-121.492900"),
)


def _shuffled(rows: tuple[tuple[str, ...], ...], *, seed: int) -> list[tuple[str, ...]]:
    rng = random.Random(seed)
    ordered = list(rows)
    rng.shuffle(ordered)
    return ordered


def generate_os_open_names_rows(seed: int = 42) -> list[dict[str, str]]:
    return [
        {"ID": id_, "NAME1": name, "GEOMETRY_X": x, "GEOMETRY_Y": y}
        for id_, name, x, y in _shuffled(_OS_OPEN_NAMES, seed=seed)
    ]


def generate_open_uprn_rows(seed: int = 42) -> list[dict[str, str]]:
    return [
        {"UPRN": uprn, "LATITUDE": lat, "LONGITUDE": lon}
        for uprn, lat, lon in _shuffled(_OPEN_UPRN, seed=seed)
    ]


def generate_code_point_open_rows(seed: int = 42) -> list[dict[str, str]]:
    return [
        {"Postcode": postcode, "Eastings": eastings, "Northings": northings}
        for postcode, eastings, northings in _shuffled(_CODE_POINT_OPEN, seed=seed)
    ]


def generate_boundary_line_rows(seed: int = 42) -> list[dict[str, str]]:
    return [
        {"GSS_CODE": gss_code, "NAME": name, "AREA_TYPE": area_type}
        for gss_code, name, area_type in _shuffled(_BOUNDARY_LINE, seed=seed)
    ]


def generate_usgs_gnis_rows(seed: int = 42) -> list[dict[str, str]]:
    return [
        {
            "FEATURE_ID": feature_id,
            "FEATURE_NAME": name,
            "FEATURE_CLASS": feature_class,
            "STATE_ALPHA": state,
            "COUNTY_NAME": county,
            "PRIM_LAT_DEC": lat,
            "PRIM_LONG_DEC": lon,
        }
        for feature_id, name, feature_class, state, county, lat, lon in _shuffled(
            _USGS_GNIS, seed=seed
        )
    ]


def generate_tiger_line_rows(seed: int = 42) -> list[dict[str, str]]:
    return [
        {
            "TLID": tlid,
            "FULLNAME": fullname,
            "LFROMHN": lfromhn,
            "LTOHN": ltohn,
            "RFROMHN": rfromhn,
            "RTOHN": rtohn,
            "MID_LAT": mid_lat,
            "MID_LON": mid_lon,
        }
        for tlid, fullname, lfromhn, ltohn, rfromhn, rtohn, mid_lat, mid_lon in _shuffled(
            _TIGER_LINE, seed=seed
        )
    ]


def generate_nad_rows(seed: int = 42) -> list[dict[str, str]]:
    return [
        {
            "NAD_ADDRESS_ID": address_id,
            "StreetAddress": street,
            "City": city,
            "State": state,
            "Zip": zip_,
            "Latitude": lat,
            "Longitude": lon,
        }
        for address_id, street, city, state, zip_, lat, lon in _shuffled(_NAD, seed=seed)
    ]
