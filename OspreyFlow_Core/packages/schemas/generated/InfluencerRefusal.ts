// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Error = "influencer_refused";
export type Influencer = string;
export type Reason = string;

/**
 * An influencer refused against the deployment's ontology, in words (never a bare 422).
 */
export interface InfluencerRefusal {
  error?: Error;
  influencer: Influencer;
  reason: Reason;
  [k: string]: unknown;
}
