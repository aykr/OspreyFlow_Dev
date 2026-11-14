// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Key = string;
export type Label = string;
export type Count = number;

export interface SearchGroup {
  key: Key;
  label: Label;
  count: Count;
  [k: string]: unknown;
}
