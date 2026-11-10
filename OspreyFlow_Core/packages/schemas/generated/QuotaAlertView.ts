// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Scope = "dataset" | "unit";
export type Key = string;
export type Day = string;
export type Words = string;

/**
 * A budget alert (decision 6): a quota's day reached its alert share.
 */
export interface QuotaAlertView {
  scope: Scope;
  key: Key;
  day: Day;
  words: Words;
}
