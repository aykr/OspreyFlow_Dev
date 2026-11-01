// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type RuleId = string;
export type RuleVersion = number;
export type Slot = string;
export type RanAt = string;
export type RunAs = string;
export type Outcome = "ran" | "refused" | "missed" | "failed";
export type Alerts = number;
export type Words = string;

/**
 * One scheduled slot of one rule, as recorded.
 */
export interface RuleRun {
  id: Id;
  rule_id: RuleId;
  rule_version: RuleVersion;
  slot: Slot;
  ran_at: RanAt;
  run_as: RunAs;
  outcome: Outcome;
  alerts?: Alerts;
  words: Words;
  [k: string]: unknown;
}
