// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Label = string;
export type Reason = string;

/**
 * An engine the deployment has that cannot answer this question, and why, in words.
 */
export interface UnusableEngine {
  name: Name;
  label: Label;
  reason: Reason;
  [k: string]: unknown;
}
