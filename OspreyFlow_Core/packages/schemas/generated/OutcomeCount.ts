// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = string;
export type Open = number;
export type Claimed = number;
export type TruePositive = number;
export type FalsePositive = number;

/**
 * Where one typology's alerts of the period stand: open, claimed, closed true or false.
 */
export interface OutcomeCount {
  typology: Typology;
  open?: Open;
  claimed?: Claimed;
  true_positive?: TruePositive;
  false_positive?: FalsePositive;
  [k: string]: unknown;
}
