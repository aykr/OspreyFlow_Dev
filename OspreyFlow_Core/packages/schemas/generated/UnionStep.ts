// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string | null;
export type Kind = "union";
/**
 * @minItems 2
 */
export type Inputs = [string, string, ...string[]];

/**
 * Stack tables with the same columns; each row keeps its own refs.
 */
export interface UnionStep {
  id: Id;
  label?: Label;
  kind: Kind;
  inputs: Inputs;
}
