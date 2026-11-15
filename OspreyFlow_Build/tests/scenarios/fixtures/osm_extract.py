"""A synthetic `.osm.pbf` file — the standing rule that fixtures are
synthetic and in-repo, generated with a seeded generator, not sourced from real intelligence data.
A real Geofabrik extract cannot be a test dependency (it is neither
synthetic nor in-repo, and CI must never depend on a network download),
so this hand-encodes the same `DenseNodes` wire shape
`services/ingest/connectors/geo/osm_pbf.py` reads — the encoder is the
mirror image of that reader, built from the same message-shape reference
(https://wiki.openstreetmap.org/wiki/PBF_Format), not a shortcut around it.

Three named settlements (`place=hamlet`, `village`, `suburb`), and a fourth
unnamed node to prove it is correctly excluded. Since the owner's ruling of 15
November 2026 the gazetteer carries settlements only, so a named node that is
not a settlement (a cafe, a farm, an island) is given with `places=` by the
test that proves it is left out.
"""

from __future__ import annotations

import zlib
from pathlib import Path
from struct import pack

from services.ingest.connectors.geo.pbf_wire import (
    encode_len_field,
    encode_packed_varints,
    encode_varint_field,
    zigzag_encode,
)

#: (name, place_kind_tag_key, place_kind_value, lat, lon) — `place_kind`
#: fields are only used to build the OSM tags here; `read_osm_places`
#: itself never emits `place_kind` (see `osm.py`'s own docstring on why).
#: Three settlements (the owner's ruling of 15 November 2026: the gazetteer carries
#: settlements only); a named node that is not one is given with `places=`.
_PLACES = [
    ("Cranford", "place", "hamlet", 51.4880, -0.4590),
    ("Hollywood", "place", "village", 52.4085, -1.8351),
    ("Harlington", "place", "suburb", 51.4870, -0.4330),
]
_UNNAMED = (52.0, -1.0)  # no `name` tag at all — must never appear in the connector's output


def _delta_encode(values: list[int]) -> list[int]:
    deltas = []
    previous = 0
    for v in values:
        deltas.append(v - previous)
        previous = v
    return deltas


def build_synthetic_osm_pbf(
    path: str | Path, places: list[tuple[str, str, str, float, float]] | None = None
) -> None:
    places = _PLACES if places is None else places
    granularity = 100
    strings = ["name"]
    tag_key_indices: dict[str, int] = {"name": 1}
    tag_value_indices: dict[str, int] = {}

    def _string_index(value: str) -> int:
        if value not in tag_value_indices:
            strings.append(value)
            tag_value_indices[value] = len(strings)
        return tag_value_indices[value]

    ids: list[int] = []
    lats: list[int] = []
    lons: list[int] = []
    keys_vals: list[int] = []

    for i, (name, kind_key, kind_val, lat, lon) in enumerate(places, start=1):
        ids.append(i)
        lats.append(round(lat * 1e9 / granularity))
        lons.append(round(lon * 1e9 / granularity))
        if kind_key not in tag_key_indices:
            strings.append(kind_key)
            tag_key_indices[kind_key] = len(strings)
        keys_vals.extend(
            [tag_key_indices["name"], _string_index(name), tag_key_indices[kind_key],
             _string_index(kind_val), 0]
        )

    # The unnamed node — no keys_vals entries at all for it (an empty tag
    # list is just the very next `0` with nothing ahead of it).
    unnamed_lat, unnamed_lon = _UNNAMED
    ids.append(len(places) + 1)
    lats.append(round(unnamed_lat * 1e9 / granularity))
    lons.append(round(unnamed_lon * 1e9 / granularity))
    keys_vals.append(0)

    stringtable = b"".join(encode_len_field(1, s.encode("utf-8")) for s in [""] + strings)

    def _zigzag_deltas(values: list[int]) -> list[int]:
        return [zigzag_encode(d) for d in _delta_encode(values)]

    dense = (
        encode_len_field(1, encode_packed_varints(_zigzag_deltas(ids)))
        + encode_len_field(8, encode_packed_varints(_zigzag_deltas(lats)))
        + encode_len_field(9, encode_packed_varints(_zigzag_deltas(lons)))
        + encode_len_field(10, encode_packed_varints(keys_vals))
    )
    primitive_group = encode_len_field(2, dense)
    primitive_block = (
        encode_len_field(1, stringtable)
        + encode_len_field(2, primitive_group)
        + encode_varint_field(17, granularity)
    )

    compressed = zlib.compress(primitive_block)
    blob = encode_varint_field(2, len(primitive_block)) + encode_len_field(3, compressed)
    blob_header = encode_len_field(1, b"OSMData") + encode_varint_field(3, len(blob))

    # A leading OSMHeader blob too, so the reader's skip-logic is actually
    # exercised rather than merely unneeded — its payload content is
    # irrelevant, since nothing reads an OSMHeader blob's fields.
    header_blob = encode_len_field(1, b"fake-header-payload")
    header_blob_header = (
        encode_len_field(1, b"OSMHeader") + encode_varint_field(3, len(header_blob))
    )

    data = (
        pack(">I", len(header_blob_header)) + header_blob_header + header_blob
        + pack(">I", len(blob_header)) + blob_header + blob
    )
    Path(path).write_bytes(data)
