// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string;
export type Lon = number;
export type Lat = number;
export type Places = MapPlace[];
export type More = boolean;

/**
 * The places found, and whether more matched than are shown: a short list is never passed off
 * as every match (rule 2). `more` is counted after the access filter, so it never says that a
 * place the reader may not see exists.
 */
export interface PlaceSearchResponse {
  places: Places;
  more: More;
  [k: string]: unknown;
}
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
