// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string;
export type Lon = number;
export type Lat = number;

/**
 * One gazetteer place: its node, its name and its point. Never the gazetteer's own
 * identifier for it (an `osm_id`, a `uprn`): a source-system identifier, which the Glass never
 * sees (rule 7).
 */
export interface MapPlace {
  id: Id;
  name: Name;
  lon: Lon;
  lat: Lat;
  [k: string]: unknown;
}
