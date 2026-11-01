// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "at_location";
export type LinkType = string;
export type Name = string;
/**
 * @minItems 3
 * @maxItems 64
 */
export type Points = [AreaPoint, AreaPoint, AreaPoint, ...AreaPoint[]];
export type Lon = number;
export type Lat = number;

/**
 * Linked by a declared link type to a `Location` whose place is inside a drawn area.
 */
export interface AtLocationRelationship {
  kind?: Kind;
  link_type: LinkType;
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
