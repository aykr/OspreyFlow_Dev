// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PromotionId = string;
export type LoadId = string;
export type DatasetId = string;
export type DatasetName = string;
export type ProposedBy = string;
export type ProposedAt = string;
export type AgeDays = number;
export type Overdue = boolean;

/**
 * A promotion waiting for review (ADR-143 decision 10), as Operations lists it: named by its
 * load and dataset, never by what it adds (rule 7).
 */
export interface WaitingPromotion {
  promotion_id: PromotionId;
  load_id: LoadId;
  dataset_id: DatasetId;
  dataset_name: DatasetName;
  proposed_by: ProposedBy;
  proposed_at: ProposedAt;
  age_days: AgeDays;
  overdue: Overdue;
  [k: string]: unknown;
}
