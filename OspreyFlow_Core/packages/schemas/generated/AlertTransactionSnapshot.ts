// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type OccurredAt = string;
export type Amount = number | null;
export type SourceName = string;
export type TargetName = string;

/**
 * A transaction an alert cites as evidence: when, how much, between whom.
 */
export interface AlertTransactionSnapshot {
  occurred_at: OccurredAt;
  amount?: Amount;
  source_name: SourceName;
  target_name: TargetName;
  [k: string]: unknown;
}
