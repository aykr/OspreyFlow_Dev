// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type AlertAfterDays = number;
export type What = string;
export type AfterDays = number;
export type Then = string;
export type Rules = AgeingRule[];
export type PromotionId = string;
export type LoadId = string;
export type DatasetId = string;
export type DatasetName = string;
export type ProposedByName = string;
export type ProposedAt = string;
export type AgeDays = number;
export type Overdue = boolean;
export type Waiting = WaitingPromotion[];
export type PromotionsRecorded = boolean;

/**
 * `GET /v1/admin/operations/ageing`: what ages and when, and the promotions waiting.
 */
export interface OperationsAgeing {
  alert_after_days: AlertAfterDays;
  rules: Rules;
  waiting?: Waiting;
  promotions_recorded?: PromotionsRecorded;
  [k: string]: unknown;
}
/**
 * One thing that ages in Operations (O3), and what happens when it does, in words.
 */
export interface AgeingRule {
  what: What;
  after_days: AfterDays;
  then: Then;
  [k: string]: unknown;
}
/**
 * A promotion waiting for review (ADR-143 decision 10), as Operations lists it: named by its
 * load and dataset, never by what it adds (rule 7).
 */
export interface WaitingPromotion {
  promotion_id: PromotionId;
  load_id: LoadId;
  dataset_id: DatasetId;
  dataset_name: DatasetName;
  proposed_by_name: ProposedByName;
  proposed_at: ProposedAt;
  age_days: AgeDays;
  overdue: Overdue;
  [k: string]: unknown;
}
