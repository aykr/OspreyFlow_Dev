// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type At = string;
export type By = string;
export type Action =
  | "engine_added"
  | "engine_edited"
  | "engine_removed"
  | "default_changed"
  | "key_set"
  | "key_rotated"
  | "key_removed"
  | "key_moved"
  | "connection_tested"
  | "limits_changed";
export type Engine = string | null;
export type Outcome = string;
export type Entries = ModelAdminEntry[];

export interface ModelAdminHistory {
  entries: Entries;
  [k: string]: unknown;
}
/**
 * One row of the engines' history. Never a key, a fragment, a hash or a length.
 */
export interface ModelAdminEntry {
  at: At;
  by: By;
  action: Action;
  engine: Engine;
  changes?: Changes;
  outcome: Outcome;
  [k: string]: unknown;
}
export interface Changes {
  [k: string]: {
    [k: string]: unknown;
  };
}
