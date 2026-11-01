// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RuleId = string;
export type RuleName = string;
export type Why = string;

/**
 * A rule that applies at load but that a dry run cannot judge, and why, in words.
 */
export interface CheckNotJudged {
  rule_id: RuleId;
  rule_name: RuleName;
  why: Why;
  [k: string]: unknown;
}
