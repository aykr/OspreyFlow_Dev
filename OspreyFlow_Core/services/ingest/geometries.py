"""The points a recipe's places stand at — the geometry partition's half of a load.

A `Location` holds a `geometry_ref`, never its coordinates (`03_CONDUIT_MIDDLEWARE.md` §5.1): the
point is a row in the analytics store's geometry partition, under that ref. The recipe engine
computes the ref and, like every Knowledge Adapter, writes nothing else, so until 9 October 2026 a
place loaded through the Ingest Studio carried a ref that resolved to nothing and was never on the
map. This module gives the run the rows to load beside the graph's nodes.

The ref and the point come from the same Knowledge Adapters the recipe names, through `REGISTRY`,
never a second copy of their arithmetic, so the node and the row cannot disagree.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from knowledge_adapters import REGISTRY
from knowledge_adapters.errors import NormalisationError
from schemas.analytics import GeometryKind, GeometryRecord
from schemas.ingest import Recipe

from .engine import RowRejected, _condition_holds, _handling, _merge_override
from .transforms import transform_name_and_part

#: The partition version a load's points are written at. The site grid's cells are at 1, and
#: nothing has written another version, so a point here is read by the default (current) read.
#: What a later gazetteer refresh does with loaded points is the question `05_DEPLOYMENT.md`
#: already raises for the site grid's cells.
POINT_GEOMETRY_VERSION = 1


def point_geometries(recipe: Recipe, rows: Iterable[Mapping[str, str]]) -> list[GeometryRecord]:
    """One point per distinct ref a `geometry_ref` binding in `recipe` gives over `rows`, marked
    with its entity's handling. A row whose coordinates do not read gives no point (the engine
    rejects that row), and so does a source with no declared coordinate system."""
    source_crs = recipe.connector.source_crs
    if source_crs is None:
        return []
    to_ref, to_lon, to_lat = (
        REGISTRY["geometry_ref"],
        REGISTRY["coordinate_lon"],
        REGISTRY["coordinate_lat"],
    )
    bindings = [
        (entity, binding.fields)
        for entity in recipe.row_template.entities
        for binding in entity.properties.values()
        if binding.transform
        and binding.fields
        and (transform_name_and_part(binding.transform) or ("", None))[0] == "geometry_ref"
    ]
    records: dict[str, GeometryRecord] = {}
    for row in rows:
        for entity, fields in bindings:
            if not _condition_holds(entity.when, row):
                continue
            try:
                raw = (row[fields[0]], row[fields[1]])
                ref = to_ref(raw, source_crs=source_crs)
                if ref in records:
                    continue
                handling = _handling(_merge_override(recipe.defaults.handling, entity.handling))
                records[ref] = GeometryRecord(
                    geometry_ref=ref,
                    version=POINT_GEOMETRY_VERSION,
                    kind=GeometryKind.POINT,
                    lon=to_lon(raw, source_crs=source_crs),
                    lat=to_lat(raw, source_crs=source_crs),
                    source_crs=source_crs,
                    source_x=float(raw[0]),
                    source_y=float(raw[1]),
                    handling=handling,
                )
            except (KeyError, NormalisationError, RowRejected):
                continue
    return list(records.values())
