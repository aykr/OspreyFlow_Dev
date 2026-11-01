// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RuleId = string;
export type RuleName = string;
export type Severity = "low" | "medium" | "high";
export type OnHit = "alert" | "hold";
export type EntityId = string;
export type EntityType = string;
export type EntityName = string;

/**
 * One alert Verify's sample would raise (decision 6): the rule, what a hit does at this
 * pipeline, and the entity matched, as the person verifying reads it in the sample.
 */
export interface WouldRaise {
  rule_id: RuleId;
  rule_name: RuleName;
  severity: Severity;
  on_hit: OnHit;
  entity_id: EntityId;
  entity_type: EntityType;
  entity_name: EntityName;
  [k: string]: unknown;
}
