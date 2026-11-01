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
export type Delisted = number;
export type Rescreened = number;
export type Alerts = number;
export type Words = string;
export type Trigger = "manual" | "schedule";

/**
 * One refresh of one list: what changed, and — counted in the reader's own organisational unit
 * alone (the owner's answer of 1 November 2026; rule 7) — how many customers its re-screening read
 * and how many alerts it raised.
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
  delisted?: Delisted;
  rescreened?: Rescreened;
  alerts?: Alerts;
  words: Words;
  trigger?: Trigger;
  [k: string]: unknown;
}
