// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Factor = string;
export type Weight = number;
export type Words = string;

/**
 * One reason a customer's baseline risk is what it is, with its weight and its words.
 */
export interface RiskFactor {
  factor: Factor;
  weight: Weight;
  words: Words;
  [k: string]: unknown;
}
