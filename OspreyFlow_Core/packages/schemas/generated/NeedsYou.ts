// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PromotionId = string;
export type LoadId = string;
export type DatasetId = string;
export type RaisedAt = string;
export type Words = string;
export type PromotionsOverdue = PromotionOverdueNotice[];
export type DatasetId1 = string;
export type DatasetName = string;
export type ToDecide = number;
export type Proposals = NeedsYouProposals[];

/**
 * The reader's *Needs you* (L2.7): their overdue promotions, served only while they are still a
 * recipient (Amendment 4 decision 11), and the proposed link types of the datasets their cases
 * load into, for a holder of `accept_types`.
 */
export interface NeedsYou {
  promotions_overdue: PromotionsOverdue;
  proposals: Proposals;
  [k: string]: unknown;
}
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
/**
 * One dataset's proposed link types in the reader's *Needs you* (ADR-145 decision 11, A2;
 * ADR-090 Amendment 4): how many the reader may read and decide. A dataset whose proposals the
 * reader is not cleared to read is not listed at all, not even as having one open (ADR-143
 * Amendment 4's *Open*, the strict reading; the orchestrator's ruling at L2.7's review).
 */
export interface NeedsYouProposals {
  dataset_id: DatasetId1;
  dataset_name: DatasetName;
  to_decide: ToDecide;
  [k: string]: unknown;
}
