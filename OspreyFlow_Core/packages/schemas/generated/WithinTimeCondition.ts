// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Op = "within_time";
export type Property = string;
export type Start = string | null;
export type End = string | null;

/**
 * A date or time property within a window; either end may be open, not both.
 */
export interface WithinTimeCondition {
  op?: Op;
  property: Property;
  start?: Start;
  end?: End;
  [k: string]: unknown;
}
