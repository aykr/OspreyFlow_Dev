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
export type Lists = ScreeningListStatus[];
export type Id = string;
export type ListName1 = string;
export type At = string;
export type Outcome = "updated" | "unchanged" | "refused" | "failed";
export type Version1 = string | null;
export type PreviousVersion = string | null;
export type Added = number;
export type Changed = number;
export type Removed = number;
export type Rescreened = number;
export type Alerts = number;
export type Words = string;
export type Updates = ScreeningListUpdate[];
export type CanManage = boolean;

export interface ScreeningLists {
  lists: Lists;
  updates: Updates;
  can_manage?: CanManage;
  [k: string]: unknown;
}
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
/**
 * One refresh of one list: what changed, and how many alerts its re-screening raised.
 */
export interface ScreeningListUpdate {
  id: Id;
  list_name: ListName1;
  at: At;
  outcome: Outcome;
  version?: Version1;
  previous_version?: PreviousVersion;
  added?: Added;
  changed?: Changed;
  removed?: Removed;
  rescreened?: Rescreened;
  alerts?: Alerts;
  words: Words;
  [k: string]: unknown;
}
