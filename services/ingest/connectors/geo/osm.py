"""The OSM-derived gazetteer connector — `spec/00_ARCHITECTURE.md` §1.2's
tier-1 gazetteer row ("OSM extract, place and address features: Place
names, roads, POIs, coarse addresses") and `spec/03_CONDUIT_MIDDLEWARE.md`
§5.1's `services/ingest/connectors/geo/`.

Every connector yields the same `Iterable[Mapping[str, str]]` row shape
`csv_connector.read_csv` does (`connectors/__init__.py`'s own docstring),
so this is what turns a parsed `.osm.pbf` into rows a recipe can bind —
`osm_gazetteer_recipe.yaml` maps them to `Location` entities through the
same `services/ingest/engine.py` every other source uses. Coordinate
reprojection is not this connector's job — `geometry_ref`'s Knowledge
Adapter handles it, with `source_crs: EPSG:4326` declared in the recipe's
`connector:` block, since OSM coordinates already are WGS84 (an identity
reprojection, not a special case: `01_DOMAIN_MODEL.md` §7.1's "these
connectors consume [reprojection], they do not rebuild it").
"""

from __future__ import annotations

from collections.abc import Iterator

from .osm_pbf import read_osm_pbf


def read_osm_places(path: str) -> Iterator[dict[str, str]]:
    """Only nodes carrying a non-empty `name` tag — an unnamed POI is not
    a gazetteer entry, the same reasoning `hmp.py`'s fixture applies to
    "structured" vs. bare records: a row with nothing to search on is not
    what this connector exists to produce. `place_kind` (from a `place=*`
    or POI tag such as `amenity`/`shop`) is deliberately not emitted here —
    `packages/ontology/default.yaml`'s v7 note records why a genuinely
    optional per-node classification can't yet bind through the recipe
    engine without a fabricated default."""
    for node in read_osm_pbf(path):
        name = node.tags.get("name")
        if not name:
            continue
        yield {
            "osm_id": str(node.osm_id),
            "name": name,
            "lat": repr(node.lat),
            "lon": repr(node.lon),
        }
