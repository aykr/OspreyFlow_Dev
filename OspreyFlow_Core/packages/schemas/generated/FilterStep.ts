// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string | null;
export type Kind = "filter";
export type Input = string;
/**
 * @minItems 1
 */
export type Keep = [FilterCondition, ...FilterCondition[]];
export type Field = string;
export type Is = ("not_null" | "null") | null;
export type Equals = string | null;
export type In = [string, ...string[]] | null;

/**
 * Keep the rows for which every condition holds; the others are counted, not lost.
 */
export interface FilterStep {
  id: Id;
  label?: Label;
  kind: Kind;
  input: Input;
  keep: Keep;
}
/**
 * One declared condition on a column: exactly one of `is`, `equals` or `in`.
 */
export interface FilterCondition {
  field: Field;
  is?: Is;
  equals?: Equals;
  in?: In;
}
