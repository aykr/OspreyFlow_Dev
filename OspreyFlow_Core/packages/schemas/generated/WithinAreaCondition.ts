// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Op = "within_area";
export type Property = string;
export type Name = string;
/**
 * @minItems 3
 * @maxItems 64
 */
export type Points = [AreaPoint, AreaPoint, AreaPoint, ...AreaPoint[]];
export type Lon = number;
export type Lat = number;

/**
 * The subject's own place inside a drawn area: a property that names a geometry (a
 * `Location`'s `geometry_ref`).
 */
export interface WithinAreaCondition {
  op?: Op;
  property: Property;
  area: DrawnArea;
  [k: string]: unknown;
}
/**
 * A drawn area: a closed outline of three to sixty-four corners, in order, the last joined
 * back to the first. `name` is what the sentence calls it ("the port area"), never matched on.
 */
export interface DrawnArea {
  name?: Name;
  points: Points;
  [k: string]: unknown;
}
export interface AreaPoint {
  lon: Lon;
  lat: Lat;
  [k: string]: unknown;
}
