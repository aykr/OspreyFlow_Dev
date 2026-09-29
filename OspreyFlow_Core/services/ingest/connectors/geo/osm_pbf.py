"""Reads `DenseNodes` out of an `.osm.pbf` file — the format every common
extract tool (osmium, osmconvert, Overpass, Geofabrik's own downloads)
emits nodes in. Message shapes: https://wiki.openstreetmap.org/wiki/PBF_Format.

**Scope, stated rather than silent.** Only tagged point nodes are read —
`ways` and `relations` (roads, building outlines, administrative boundary
polygons) are not parsed. That is the right slice for a *gazetteer*
connector (`osm.py`'s job is "Place names ... POIs, coarse addresses" per
`00_ARCHITECTURE.md` §1.2's tier-1 gazetteer row): named point places.
Roads and polygon boundaries are a separate, later capability (tier 4's
OGC features / the UK-US gazetteer connectors' boundary sources,
built later), not something this
connector silently drops from an otherwise-complete parse — it never
reads a `PrimitiveGroup`'s `ways`/`relations` fields at all. Plain (as
opposed to dense) `Node` messages are equally out of scope: no extractor
in common use emits them, so a real Geofabrik/osmium extract never needs
that path, and testing it would need a fixture no real file resembles.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from struct import unpack

from .pbf_wire import WIRE_LEN, iter_fields, iter_packed_varints, zigzag_decode

_OSM_DATA_BLOB_TYPE = b"OSMData"


@dataclass(frozen=True)
class OsmNode:
    osm_id: int
    lat: float
    lon: float
    tags: dict[str, str]


def _read_blobs(data: bytes) -> Iterator[bytes]:
    """Yields the decompressed payload of every `OSMData` blob, skipping
    the leading `OSMHeader` blob (bounding box / required-feature
    metadata this connector has no use for)."""
    pos = 0
    while pos < len(data):
        (header_len,) = unpack(">I", data[pos : pos + 4])
        pos += 4
        header = data[pos : pos + header_len]
        pos += header_len

        blob_type = None
        datasize = None
        for field_number, _wire_type, value in iter_fields(header):
            if field_number == 1:
                blob_type = value
            elif field_number == 3:
                datasize = value
        assert datasize is not None, "BlobHeader missing its declared datasize"

        blob = data[pos : pos + datasize]
        pos += datasize
        if blob_type != _OSM_DATA_BLOB_TYPE:
            continue

        raw: bytes | None = None
        zlib_data: bytes | None = None
        for field_number, _wire_type, value in iter_fields(blob):
            if field_number == 1:
                raw = value  # type: ignore[assignment]
            elif field_number == 3:
                zlib_data = value  # type: ignore[assignment]
        yield raw if raw is not None else zlib.decompress(zlib_data or b"")


def _string_table(data: bytes) -> list[str]:
    """Index 0 is reserved (conventionally empty) — `keys_vals`'s `0`
    sentinel below relies on no real key ever indexing to it."""
    strings: list[str] = []
    for field_number, wire_type, value in iter_fields(data):
        if field_number == 1 and wire_type == WIRE_LEN:
            assert isinstance(value, bytes)
            strings.append(value.decode("utf-8"))
    return strings


def _dense_nodes(
    data: bytes, strings: list[str], granularity: int, lat_offset: int, lon_offset: int
) -> Iterator[OsmNode]:
    ids: list[int] = []
    lats: list[int] = []
    lons: list[int] = []
    keys_vals: list[int] = []
    for field_number, wire_type, value in iter_fields(data):
        if wire_type != WIRE_LEN:
            continue  # `denseinfo` (field 5) is the only non-packed sub-message here; skipped
        if field_number == 1:
            ids = [zigzag_decode(v) for v in iter_packed_varints(value)]  # type: ignore[arg-type]
        elif field_number == 8:
            lats = [zigzag_decode(v) for v in iter_packed_varints(value)]  # type: ignore[arg-type]
        elif field_number == 9:
            lons = [zigzag_decode(v) for v in iter_packed_varints(value)]  # type: ignore[arg-type]
        elif field_number == 10:
            keys_vals = list(iter_packed_varints(value))  # type: ignore[arg-type]

    tag_groups = _split_on_zero(keys_vals)
    running_id = running_lat = running_lon = 0
    for i, (delta_id, delta_lat, delta_lon) in enumerate(zip(ids, lats, lons, strict=True)):
        running_id += delta_id
        running_lat += delta_lat
        running_lon += delta_lon
        tags: dict[str, str] = {}
        if i < len(tag_groups):
            pairs = tag_groups[i]
            tags = {strings[pairs[j]]: strings[pairs[j + 1]] for j in range(0, len(pairs), 2)}
        yield OsmNode(
            osm_id=running_id,
            lat=1e-9 * (lat_offset + granularity * running_lat),
            lon=1e-9 * (lon_offset + granularity * running_lon),
            tags=tags,
        )


def _split_on_zero(keys_vals: list[int]) -> list[list[int]]:
    """`keys_vals` has no length prefix per node — a `0` (string-table
    index 0, reserved/empty) separates one node's key/value index pairs
    from the next. An empty `keys_vals` altogether (no node in this block
    carries any tag) is valid and yields no groups at all."""
    groups: list[list[int]] = []
    current: list[int] = []
    for v in keys_vals:
        if v == 0:
            groups.append(current)
            current = []
        else:
            current.append(v)
    return groups


def read_osm_pbf(path: str) -> Iterator[OsmNode]:
    with open(path, "rb") as handle:
        data = handle.read()

    for block in _read_blobs(data):
        strings: list[str] = []
        granularity = 100
        lat_offset = 0
        lon_offset = 0
        groups: list[bytes] = []
        for field_number, _wire_type, value in iter_fields(block):
            if field_number == 1:
                strings = _string_table(value)  # type: ignore[arg-type]
            elif field_number == 2:
                groups.append(value)  # type: ignore[arg-type]
            elif field_number == 17:
                granularity = value  # type: ignore[assignment]
            elif field_number == 19:
                lat_offset = value  # type: ignore[assignment]
            elif field_number == 20:
                lon_offset = value  # type: ignore[assignment]

        for group in groups:
            for field_number, _wt, value in iter_fields(group):
                if field_number == 2:  # PrimitiveGroup.dense
                    yield from _dense_nodes(
                        value, strings, granularity, lat_offset, lon_offset  # type: ignore[arg-type]
                    )
