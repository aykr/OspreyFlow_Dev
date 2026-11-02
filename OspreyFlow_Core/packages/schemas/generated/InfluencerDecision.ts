// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Words = string;

/**
 * Sending a waiting version back (or its proposer withdrawing it), in words.
 */
export interface InfluencerDecision {
  words: Words;
  [k: string]: unknown;
}
