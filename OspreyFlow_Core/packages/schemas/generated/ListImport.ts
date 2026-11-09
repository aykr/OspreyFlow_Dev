// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ListId = string;
export type Outcome = "updated" | "unchanged" | "refused" | "failed";
export type Version = number | null;
export type PreviousVersion = number | null;
export type Added = number;
export type Changed = number;
export type Delisted = number;
export type Trigger = "manual" | "schedule";
export type Words = string;

/**
 * One import or refresh: what it did, in words, and what it changed.
 */
export interface ListImport {
  list_id: ListId;
  outcome: Outcome;
  version?: Version;
  previous_version?: PreviousVersion;
  added?: Added;
  changed?: Changed;
  delisted?: Delisted;
  trigger?: Trigger;
  words: Words;
  [k: string]: unknown;
}
