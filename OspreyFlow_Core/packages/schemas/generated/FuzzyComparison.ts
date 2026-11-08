// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Left = string;
export type Right = string;
export type Method = "exact" | "jaro_winkler" | "levenshtein";

/**
 * One comparison: a column of the left table against a column of the right, by a method.
 */
export interface FuzzyComparison {
  left: Left;
  right: Right;
  method: Method;
}
