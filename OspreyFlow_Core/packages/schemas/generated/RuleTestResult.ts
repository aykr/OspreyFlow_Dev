// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RuleId = string;
export type Version = number;
export type Days = number;
export type WouldRaise = number;
export type Words = string;

/**
 * *Test* (ADR-146 decision 3): how many alerts the draft would have raised over the dataset's
 * last `days` days, run as its author, and the version it ran on.
 */
export interface RuleTestResult {
  rule_id: RuleId;
  version: Version;
  days: Days;
  would_raise: WouldRaise;
  words: Words;
  [k: string]: unknown;
}
