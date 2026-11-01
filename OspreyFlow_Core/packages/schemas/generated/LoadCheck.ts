// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RuleId = string;
export type OnHit = "alert" | "hold";

/**
 * One rule attached to a pipeline, by its id, and what a hit does there. It names a rule; it
 * cannot carry one (`extra="forbid"`): engineers attach rules, they do not write them.
 */
export interface LoadCheck {
  rule_id: RuleId;
  on_hit?: OnHit;
}
