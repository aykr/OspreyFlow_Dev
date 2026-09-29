// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type GeometryRef = string;
export type Version = number;
/**
 * A known-gaps closure: `GeometryRecord` was
 * point-only through Phase 2/5 Checkpoint 3c. `POLYGON` is the boundary/jurisdiction shape a
 * `Location` with no single point (a ward, an administrative area — see
 * `packages/ontology/default.yaml`'s own "a jurisdiction... must be able
 * to carry none at all" allowance for `geometry_ref`) can now carry.
 */
export type GeometryKind = "point" | "polygon";
export type Lon = number | null;
export type Lat = number | null;
export type SourceCrs = string | null;
export type SourceX = number | null;
export type SourceY = number | null;
export type GeometryWkb = string | null;
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;

/**
 * One row in the analytics store's geometry reference partition —
 * `03_CONDUIT_MIDDLEWARE.md` §5.1: "the geometry column lives in the
 * analytics store where spatial predicates are cheap, and the graph
 * holds the Location node with a reference to it." `geometry_ref` is
 * that reference's value: for a `POINT` row, produced by the
 * `geometry_ref`/`grid_ref` Knowledge Adapters (`01_DOMAIN_MODEL.md`
 * §7.1) as a deterministic hash of `(source_crs, source_x, source_y)` —
 * the same source coordinate always yields the same ref, so a recipe
 * re-run never mints a second row for the same point.
 *
 * Never written on a graph `Location` node directly — putting geometry
 * on the graph node would make spatial filtering a traversal, the wrong
 * shape of query. A `Location.geometry_ref` property (a plain string)
 * points at exactly one row here; the row itself carries the reprojected
 * WGS84 point and the retained original, the same `value_raw` discipline
 * every other Knowledge Adapter follows.
 *
 * No `investigation_scope` here, unlike `EventRecord`: reference/gazetteer
 * data is versioned as a whole rather than scoped per investigation
 * (`03_CONDUIT_MIDDLEWARE.md` §5.1's "reference partition") — a gazetteer
 * refresh loads a new `version` of the *whole* partition rather than
 * merging into the previous one, and every prior version's rows are
 * retained (never overwritten) so an investigation can still resolve
 * against the gazetteer version that was in force when a place name was
 * matched. `AnalyticsPort.get_geometry`/`get_geometries` default to the
 * partition's current version (the highest `version` present) and accept
 * an explicit older one to pin a historical read.
 *
 * `handling` **is** carried per row, unlike the note this docstring used
 * to make — this partition now has a real,
 * access-controlled read path, and geometry is not uniformly public
 * reference data: a site's own control-point/grid geometry (the HMP
 * case) is exactly as sensitive as the `Location` entities it backs, so
 * it needs the same per-row handling discipline `EventRecord` already
 * has, checked by the same `AccessFilter` (`01_DOMAIN_MODEL.md` §2.2).
 *
 * **`kind` discriminates `POINT` from `POLYGON` (Phase 5's known-gaps closure).** A `POINT`
 * row carries `lon`/`lat` (and, optionally, the retained original
 * `source_crs`/`source_x`/`source_y`) and no `geometry_wkb`. A `POLYGON`
 * row — a boundary with no single point — carries `geometry_wkb` (WKB
 * bytes; the DuckDB adapter stores/reads these via its `spatial`
 * extension's `ST_GeomFromWKB`/`ST_AsWKB`) and no `lon`/`lat`. The two
 * shapes are mutually exclusive, enforced below, rather than a `POLYGON`
 * row carrying a meaningless centroid or a `POINT` row carrying an unused
 * WKB column.
 */
export interface GeometryRecord {
  geometry_ref: GeometryRef;
  version: Version;
  kind?: GeometryKind;
  lon?: Lon;
  lat?: Lat;
  source_crs?: SourceCrs;
  source_x?: SourceX;
  source_y?: SourceY;
  geometry_wkb?: GeometryWkb;
  handling: Handling;
  [k: string]: unknown;
}
export interface Handling {
  classification: Classification;
  handling_code: HandlingCode;
  action_code?: ActionCode;
  sanitisation_code?: SanitisationCode;
  originator: OrgUnitId;
  owning_unit: OrgUnitId;
  review_date?: ReviewDate;
  legal_basis?: LegalBasis;
  [k: string]: unknown;
}
