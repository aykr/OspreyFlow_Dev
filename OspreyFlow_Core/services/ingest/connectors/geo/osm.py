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

#: The `place=*` values that are settlements: where people live, from a city to a lone house,
#: and the named parts of a town (https://wiki.openstreetmap.org/wiki/Key:place, "Populated
#: settlements, urban and rural"). The owner's ruling, 15 November 2026: the gazetteer carries
#: settlements only, not every named point (about 900,000 for Great Britain). Not a settlement:
#: `farm`, `allotments`, `locality` (an unpopulated named place), `island`, `square`, `plot`,
#: `city_block`, and every POI.
SETTLEMENT_PLACES = frozenset(
    {"city", "borough", "town", "village", "hamlet", "isolated_dwelling", "suburb", "quarter",
     "neighbourhood"}
)  # fmt: skip


def read_osm_places(path: str) -> Iterator[dict[str, str]]:
    """Only named settlements: nodes whose `place` tag is one of `SETTLEMENT_PLACES` and that
    carry a non-empty `name` (an unnamed node has nothing to search on). `place_kind` is
    deliberately not emitted here: `packages/ontology/default.yaml`'s v7 note records why a
    genuinely optional per-node classification can't yet bind through the recipe engine without a
    fabricated default."""
    for node in read_osm_pbf(path):
        name = node.tags.get("name")
        if not name or node.tags.get("place") not in SETTLEMENT_PLACES:
            continue
        yield {
            "osm_id": str(node.osm_id),
            "name": name,
            "lat": repr(node.lat),
            "lon": repr(node.lon),
        }
