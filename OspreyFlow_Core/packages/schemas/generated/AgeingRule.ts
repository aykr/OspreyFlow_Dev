// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type What = string;
export type AfterDays = number;
export type Then = string;

/**
 * One thing that ages in Operations (O3), and what happens when it does, in words.
 */
export interface AgeingRule {
  what: What;
  after_days: AfterDays;
  then: Then;
  [k: string]: unknown;
}
