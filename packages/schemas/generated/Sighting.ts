// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type OccurredAt = string;
export type Lat = number;
export type Lon = number;

export interface Sighting {
  occurred_at: OccurredAt;
  lat: Lat;
  lon: Lon;
  [k: string]: unknown;
}
