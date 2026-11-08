// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PromotionId = string;
export type LoadId = string;
export type DatasetId = string;
export type RaisedAt = string;
export type Recipients = string[];
export type Words = string;

/**
 * *Promotions overdue* (ADR-145 Amendment 4 decision 11, R7), raised once per promotion at N
 * days to the dataset's Authors holding `review_promotions` and to administrators. Its words name
 * the load and the dataset, never the promotion's contents (rule 7).
 */
export interface PromotionOverdueAlert {
  promotion_id: PromotionId;
  load_id: LoadId;
  dataset_id: DatasetId;
  raised_at: RaisedAt;
  recipients: Recipients;
  words: Words;
  [k: string]: unknown;
}
