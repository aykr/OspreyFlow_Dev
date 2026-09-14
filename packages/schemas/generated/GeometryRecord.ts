// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
export type GeometryRef = string;
export type Lon = number;
export type Lat = number;
export type SourceCrs = string;
export type SourceX = number | null;
export type SourceY = number | null;

/**
 * One row in the analytics store's geometry reference partition —
 * `03_CONDUIT_MIDDLEWARE.md` §5.1: "the geometry column lives in the
 * analytics store where spatial predicates are cheap, and the graph
 * holds the Location node with a reference to it." `geometry_ref` is
 * that reference's value, produced by the `geometry_ref`/`grid_ref`
 * Knowledge Adapters (`01_DOMAIN_MODEL.md` §7.1) as a deterministic hash
 * of `(source_crs, source_x, source_y)` — the same source coordinate
 * always yields the same ref, so a recipe re-run never mints a second
 * row for the same point.
 *
 * Never written on a graph `Location` node directly — putting geometry
 * on the graph node would make spatial filtering a traversal, the wrong
 * shape of query. A `Location.geometry_ref` property (a plain string)
 * points at exactly one row here; the row itself carries the reprojected
 * WGS84 point and the retained original, the same `value_raw` discipline
 * every other Knowledge Adapter follows.
 *
 * No `investigation_scope`/`handling` here, unlike `EventRecord`:
 * reference/gazetteer data is versioned as a whole rather than scoped
 * per investigation (`03_CONDUIT_MIDDLEWARE.md` §5.1's "reference
 * partition"), and the full versioning/access-control story for that
 * partition is Phase 5 scope (`07_BUILD_PLAN.md`), the same phase that
 * builds the geospatial connectors and the site grid this table also
 * serves. Phase 2 establishes the correct storage tier and shape; it
 * does not build a read path with its own access control for it.
 */
export interface GeometryRecord {
  geometry_ref: GeometryRef;
  lon: Lon;
  lat: Lat;
  source_crs: SourceCrs;
  source_x?: SourceX;
  source_y?: SourceY;
  [k: string]: unknown;
}
