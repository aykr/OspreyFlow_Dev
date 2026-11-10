// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RecipeId = string;
export type Chosen = boolean;
export type RuleId = string;
export type OnHit = "alert" | "hold";
export type Checks = LoadCheck[];
export type RuleId1 = string;
export type Name = string;
export type Words = string;
export type Scope = "this_case" | "deployment";
export type Trigger = "pre_commit" | "post_commit" | "schedule" | "list_refresh";
export type Severity = "low" | "medium" | "high";
export type Status = "pending" | "active";
export type CanHold = boolean;
export type AlwaysApplies = boolean;
export type AuthorsOnHit = "alert" | "hold";
export type Available = LoadCheckRule[];
export type SetBy = string | null;
export type SetAt = string | null;

/**
 * The pipeline's "Checks on load" step. `chosen` is false until an engineer has chosen: then
 * every case rule judges the pipeline's loads, as before the step existed.
 */
export interface LoadChecksView {
  recipe_id: RecipeId;
  chosen: Chosen;
  checks?: Checks;
  available?: Available;
  set_by?: SetBy;
  set_at?: SetAt;
  [k: string]: unknown;
}
/**
 * One rule attached to a pipeline, by its id, and what a hit does there. It names a rule; it
 * cannot carry one (`extra="forbid"`): engineers attach rules, they do not write them.
 */
export interface LoadCheck {
  rule_id: RuleId;
  on_hit?: OnHit;
}
/**
 * A load-time rule the engineer may attach, as the rules list shows it: its name, its sentence
 * or typology in words, its scope, when it runs and how urgent its alerts are.
 */
export interface LoadCheckRule {
  rule_id: RuleId1;
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
