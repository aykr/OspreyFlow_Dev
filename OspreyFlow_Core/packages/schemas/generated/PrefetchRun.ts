// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Area = string;
export type ProviderId = string;
export type At = string;
export type TilesFetched = number;
export type TilesAlreadyCached = number;
export type Failed = string | null;

/**
 * One area's last run: counts only.
 */
export interface PrefetchRun {
  area: Area;
  provider_id: ProviderId;
  at: At;
  tiles_fetched: TilesFetched;
  tiles_already_cached: TilesAlreadyCached;
  failed?: Failed;
  [k: string]: unknown;
}
