// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Approve = boolean;
export type Reason = string | null;

/**
 * *Approve and commit*, or *Reject with a reason* (a reason is required to reject).
 */
export interface PromotionDecision {
  approve: Approve;
  reason?: Reason;
}
