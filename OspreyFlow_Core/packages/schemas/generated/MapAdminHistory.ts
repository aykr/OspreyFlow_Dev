// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type At = string;
export type By = string;
export type Action =
  | "provider_added"
  | "provider_edited"
  | "provider_removed"
  | "default_changed"
  | "key_set"
  | "key_removed"
  | "areas_changed"
  | "schedule_changed"
  | "prefetch_run"
  | "basemap_built"
  | "basemap_verified";
export type Provider = string | null;
export type Outcome = string;
export type Entries = MapAdminEntry[];

export interface MapAdminHistory {
  entries: Entries;
  [k: string]: unknown;
}
/**
 * One row of the maps' history. Never a key, a fragment, a hash or a length.
 */
export interface MapAdminEntry {
  at: At;
  by: By;
  action: Action;
  provider?: Provider;
  changes?: Changes;
  outcome: Outcome;
  [k: string]: unknown;
}
export interface Changes {
  [k: string]: {
    [k: string]: unknown;
  };
}
