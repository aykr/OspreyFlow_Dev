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
export type Tiles = number;
export type Area = string;
export type ProviderId1 = string;
export type At = string;
export type TilesFetched = number;
export type TilesAlreadyCached = number;
export type Failed = string | null;

export interface PrefetchAreaView {
  area: PrefetchArea;
  tiles: Tiles;
  last_run?: PrefetchRun | null;
  [k: string]: unknown;
}
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
/**
 * One area's last run: counts only.
 */
export interface PrefetchRun {
  area: Area;
  provider_id: ProviderId1;
  at: At;
  tiles_fetched: TilesFetched;
  tiles_already_cached: TilesAlreadyCached;
  failed?: Failed;
  [k: string]: unknown;
}
