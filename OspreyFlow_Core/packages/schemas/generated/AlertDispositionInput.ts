// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Disposition = "true_positive" | "false_positive";
export type Reason = string;

export interface AlertDispositionInput {
  disposition: Disposition;
  reason: Reason;
  [k: string]: unknown;
}
