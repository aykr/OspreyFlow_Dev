// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ListName = string;
export type Source = "ofac_sdn" | "ofsi_consolidated" | "un_consolidated" | "eu_consolidated" | "opensanctions";
export type Location = string;
export type Dataset = string | null;
export type Synthetic = boolean;
export type Licence = string;
export type Version = string | null;
export type Entries = number;
export type UpdatedAt = string | null;
export type AttemptedAt = string | null;
export type Failure = string | null;

/**
 * One list as the Lists screen shows it: its version, entries, last update and the failure of
 * its last attempt, in words.
 */
export interface ScreeningListStatus {
  list_name: ListName;
  source: Source;
  location: Location;
  dataset?: Dataset;
  synthetic: Synthetic;
  licence: Licence;
  version?: Version;
  entries?: Entries;
  updated_at?: UpdatedAt;
  attempted_at?: AttemptedAt;
  failure?: Failure;
  [k: string]: unknown;
}
