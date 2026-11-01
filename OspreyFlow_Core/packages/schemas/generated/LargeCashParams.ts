// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "large_cash";
export type Threshold = number;
/**
 * @minItems 1
 */
export type CashTypes = ["CASH_IN" | "CASH_OUT", ...("CASH_IN" | "CASH_OUT")[]];

/**
 * A cash movement (paid in, or drawn out) at or over the threshold.
 */
export interface LargeCashParams {
  typology?: Typology;
  threshold: Threshold;
  cash_types?: CashTypes;
  [k: string]: unknown;
}
