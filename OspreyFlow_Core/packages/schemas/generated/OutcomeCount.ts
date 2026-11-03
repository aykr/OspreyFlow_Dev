// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = string;
export type Open = number;
export type Claimed = number;
export type TruePositive = number;
export type FalsePositive = number;
export type Duplicate = number;
export type NoFurtherAction = number;
export type Referred = number;
export type Closed = number;

/**
 * Where one typology's alerts of the period stand: open, claimed, closed with each closing
 * reason (ADR-133 Amendment 5), or closed with none (taken back). Build order step 18c: a close
 * as Duplicate, No further action or Referred, or with no outcome, was counted as open.
 */
export interface OutcomeCount {
  typology: Typology;
  open?: Open;
  claimed?: Claimed;
  true_positive?: TruePositive;
  false_positive?: FalsePositive;
  duplicate?: Duplicate;
  no_further_action?: NoFurtherAction;
  referred?: Referred;
  closed?: Closed;
  [k: string]: unknown;
}
