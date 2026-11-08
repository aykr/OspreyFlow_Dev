// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type ProviderId = string;
export type West = number;
export type South = number;
export type East = number;
export type North = number;
export type ZoomMin = number;
export type ZoomMax = number;

/**
 * A named box whose tiles are fetched ahead of use, for one proxied, cached provider
 * (ADR-147 decision 5). Degrees, WGS84; zooms inclusive.
 */
export interface PrefetchArea {
  name: Name;
  provider_id: ProviderId;
  west: West;
  south: South;
  east: East;
  north: North;
  zoom_min: ZoomMin;
  zoom_max: ZoomMax;
}
