// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RuleId = string;
export type Schedule = string;
export type State = "draft" | "scheduled" | "stopped" | "waiting_for_approval";
export type Words = string | null;
export type NextRun = string | null;
export type Id = string;
export type RuleId1 = string;
export type RuleVersion = number;
export type Slot = string;
export type RanAt = string;
export type RunAs = string;
export type Outcome = "ran" | "refused" | "missed" | "failed";
export type Alerts = number;
export type Words1 = string;
export type Runs = RuleRun[];

/**
 * A scheduled rule's schedule, in words, with its next run and its latest runs. A schedule
 * that will not run says why (`state` and `words`), never only a missing next run.
 */
export interface RuleScheduleView {
  rule_id: RuleId;
  schedule: Schedule;
  state: State;
  words?: Words;
  next_run?: NextRun;
  runs?: Runs;
  [k: string]: unknown;
}
/**
 * One scheduled slot of one rule, as recorded.
 */
export interface RuleRun {
  id: Id;
  rule_id: RuleId1;
  rule_version: RuleVersion;
  slot: Slot;
  ran_at: RanAt;
  run_as: RunAs;
  outcome: Outcome;
  alerts?: Alerts;
  words: Words1;
  [k: string]: unknown;
}
