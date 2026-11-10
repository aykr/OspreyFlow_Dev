// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RuleId = string;
export type Name = string;
export type Words = string;
export type Scope = "this_case" | "deployment";
export type Trigger = "pre_commit" | "post_commit" | "schedule" | "list_refresh";
export type Severity = "low" | "medium" | "high";
export type Status = "pending" | "active";
export type CanHold = boolean;
export type AlwaysApplies = boolean;
export type AuthorsOnHit = "alert" | "hold";

/**
 * A load-time rule the engineer may attach, as the rules list shows it: its name, its sentence
 * or typology in words, its scope, when it runs and how urgent its alerts are.
 */
export interface LoadCheckRule {
  rule_id: RuleId;
  name: Name;
  words: Words;
  scope: Scope;
  trigger: Trigger;
  severity: Severity;
  status: Status;
  can_hold: CanHold;
  always_applies: AlwaysApplies;
  authors_on_hit: AuthorsOnHit;
  [k: string]: unknown;
}
