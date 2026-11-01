// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Disposition = "true_positive" | "false_positive";
export type Reason = string;

/**
 * Closing an alert (ADR-133 decision 7: "closing needs a reason"). A reason of only spaces is
 * no reason: it is refused as an empty one is.
 */
export interface AlertDispositionInput {
  disposition: Disposition;
  reason: Reason;
  [k: string]: unknown;
}
