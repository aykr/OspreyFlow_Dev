"""`coordinate_lon` / `coordinate_lat` / `geometry_ref` — `00_ARCHITECTURE.md`
§1.2.2, `03_CONDUIT_MIDDLEWARE.md` §5.1, ADR-017. Reprojects a source
coordinate pair to WGS84 (EPSG:4326), the canonical projection for every
coordinate stored in the graph and the event tables.

The source CRS is never guessed. UK authoritative data is overwhelmingly
OSGB36 British National Grid (EPSG:27700); US authoritative data is very
often NAD83 State Plane, with the zone varying by state and sometimes
within one. Guessing between them silently places a point hundreds of
miles from where it belongs, and the result looks like ordinary data
rather than an error — the same failure shape `datetime`'s ambiguous
`date_order` guards against, for the same reason: with both countries in
scope there is no safe default. The connector profile declares
`source_crs`; a coordinate pair with no declared and no self-describing
CRS is rejected, named and counted, exactly like an undated offset.

**`coordinate_lon`/`coordinate_lat`** are the general-purpose reprojection
pair — two adapters rather than one returning a compound result, matching
the `value_raw`/`value_normalised` pattern (two bindings reading the same
source fields) rather than teaching every property-writing path in the
engine to unpack a result type. They feed an `EventRecord.lat`/`lon` (the
analytics store's own event-level geometry) or any other property that
genuinely wants a bare coordinate.

**`geometry_ref` is the one a `Location` node actually binds.**
`03_CONDUIT_MIDDLEWARE.md` §5.1: geometry is stored once, in the analytics
store's geometry reference partition, and the graph's `Location` node
holds a reference to it, never the coordinates themselves — putting
geometry on the graph node would make spatial filtering a traversal, the
wrong shape of query. `geometry_ref` reprojects exactly like
`coordinate_lon`/`coordinate_lat` and returns a deterministic reference
string derived from `(source_crs, x, y)` — the same source coordinate
always yields the same ref, which is what makes a recipe re-run idempotent
here the same way CDR deduplication is. The matching `GeometryRecord`
(`schemas/analytics.py`) — the reprojected point plus the retained
original — is what a caller writes into the analytics store's geometry
table under that ref; this adapter only computes the ref and the
coordinates, it does not write anywhere itself (no Knowledge Adapter
does).
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

from pyproj import Transformer
from pyproj.exceptions import CRSError

from .errors import NormalisationError

_WGS84 = "EPSG:4326"


@lru_cache(maxsize=32)
def _transformer(source_crs: str) -> Transformer:
    return Transformer.from_crs(source_crs, _WGS84, always_xy=True)


def reproject_point(x: float, y: float, *, source_crs: str) -> tuple[float, float]:
    """The float-in, float-out reprojection primitive — shared with
    `grid_ref`, which parses its own coordinates from a different input
    shape and has no need to round-trip them through strings first."""
    sample = f"{x},{y}"
    try:
        transformer = _transformer(source_crs)
    except CRSError as exc:
        raise NormalisationError(
            "coordinates", sample, f"unrecognised coordinate reference system: {source_crs!r}"
        ) from exc

    lon, lat = transformer.transform(x, y)
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise NormalisationError(
            "coordinates",
            sample,
            f"reprojection from {source_crs} fell outside WGS84 bounds — "
            "the source_crs is very likely wrong for this data",
        )
    return lon, lat


def geometry_reference(source_crs: str, x: float, y: float) -> str:
    """A deterministic id for one source coordinate — the same
    `(source_crs, x, y)` always yields the same ref, so re-running a
    recipe against the same source never mints a second geometry record
    for the same point. Not a secret or an access-controlled value; a
    plain content hash is the right tool, not a ULID."""
    digest = hashlib.sha256(f"{source_crs}|{x}|{y}".encode()).hexdigest()
    return f"geo:{digest[:16]}"


def _reproject(
    raw: tuple[str, str], *, source_crs: str | None
) -> tuple[float, float, float, float]:
    """Returns `(lon, lat, x, y)` — the reprojected point and the parsed
    original, so every caller below gets both without re-parsing."""
    sample = f"{raw[0]},{raw[1]}"
    if source_crs is None:
        raise NormalisationError(
            "coordinates",
            sample,
            "ambiguous coordinate reference system — the connector profile must "
            "declare source_crs before a coordinate pair can be reprojected",
        )
    try:
        x, y = float(raw[0]), float(raw[1])
    except ValueError as exc:
        raise NormalisationError("coordinates", sample, "not a numeric coordinate pair") from exc

    lon, lat = reproject_point(x, y, source_crs=source_crs)
    return lon, lat, x, y


def coordinate_lon(raw: tuple[str, ...], *, source_crs: str | None = None) -> float:
    lon, _lat, _x, _y = _reproject((raw[0], raw[1]), source_crs=source_crs)
    return lon


def coordinate_lat(raw: tuple[str, ...], *, source_crs: str | None = None) -> float:
    _lon, lat, _x, _y = _reproject((raw[0], raw[1]), source_crs=source_crs)
    return lat


def geometry_ref(raw: tuple[str, ...], *, source_crs: str | None = None) -> str:
    _lon, _lat, x, y = _reproject((raw[0], raw[1]), source_crs=source_crs)
    assert source_crs is not None  # _reproject already rejected the None case
    return geometry_reference(source_crs, x, y)
