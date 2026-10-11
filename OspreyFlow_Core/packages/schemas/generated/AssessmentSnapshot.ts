// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type JudgementId = string;
export type Statement = string;
export type ProbabilityBand = string;
export type Supporting = string[];
export type Contradicting = string[];
export type Author = string;
export type CreatedAt = string;

/**
 * A judgement as it was written when it was added — later edits to the judgement do not reach
 * the pack.
 */
export interface AssessmentSnapshot {
  judgement_id: JudgementId;
  statement: Statement;
  probability_band: ProbabilityBand;
  supporting?: Supporting;
  contradicting?: Contradicting;
  author: Author;
  created_at: CreatedAt;
  [k: string]: unknown;
}
