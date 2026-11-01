// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Reason = string;

/**
 * Rejecting (or, by its own proposer, withdrawing) a change waiting for approval.
 */
export interface RuleChangeRejection {
  reason: Reason;
}
