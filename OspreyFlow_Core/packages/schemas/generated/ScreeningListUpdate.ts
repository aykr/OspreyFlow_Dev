// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type ListName = string;
export type At = string;
export type Outcome = "updated" | "unchanged" | "refused" | "failed";
export type Version = string | null;
export type PreviousVersion = string | null;
export type Added = number;
export type Changed = number;
export type Removed = number;
export type Rescreened = number;
export type Alerts = number;
export type Words = string;
export type Trigger = "manual" | "schedule";

/**
 * One refresh of one list: what changed, and how many alerts its re-screening raised.
 */
export interface ScreeningListUpdate {
  id: Id;
  list_name: ListName;
  at: At;
  outcome: Outcome;
  version?: Version;
  previous_version?: PreviousVersion;
  added?: Added;
  changed?: Changed;
  removed?: Removed;
  rescreened?: Rescreened;
  alerts?: Alerts;
  words: Words;
  trigger?: Trigger;
  [k: string]: unknown;
}
