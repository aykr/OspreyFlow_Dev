"""Geospatial connectors — `docs/03_CONDUIT_MIDDLEWARE.md` §5.1:
"Gazetteers, boundary files and OSM extracts enter through
`services/ingest/connectors/geo/` (GeoPackage, Shapefile, GeoJSON,
CSV-with-coordinates, OSM PBF, and WFS)." Only OSM PBF lands in Phase 5's
first checkpoint (`osm.py`); the rest follow the same
`Iterable[Mapping[str, str]]` row shape every other connector uses.
"""
