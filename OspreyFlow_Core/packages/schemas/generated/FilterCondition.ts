// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Field = string;
export type Is = ("not_null" | "null") | null;
export type Equals = string | null;
export type In = [string, ...string[]] | null;

/**
 * One declared condition on a column: exactly one of `is`, `equals` or `in`.
 */
export interface FilterCondition {
  field: Field;
  is?: Is;
  equals?: Equals;
  in?: In;
}
