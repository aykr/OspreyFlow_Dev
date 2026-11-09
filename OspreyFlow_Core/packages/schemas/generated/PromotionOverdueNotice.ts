// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PromotionId = string;
export type LoadId = string;
export type DatasetId = string;
export type RaisedAt = string;
export type Words = string;

/**
 * One *Promotions overdue* alert as its recipient reads it (L2.7's *Needs you*): the alert
 * without its recipients, since who else was alerted is not that person's to read.
 */
export interface PromotionOverdueNotice {
  promotion_id: PromotionId;
  load_id: LoadId;
  dataset_id: DatasetId;
  raised_at: RaisedAt;
  words: Words;
  [k: string]: unknown;
}
