// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Left = string;
export type Right = string;
export type Method = "exact" | "soundex" | "year";

/**
 * Only pairs agreeing on this key are compared (as the ontology's `resolution.blocking`).
 */
export interface FuzzyBlocking {
  left: Left;
  right: Right;
  method?: Method;
}
