// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Op = "above";
export type Property = string;
export type Value = number;

export interface AboveCondition {
  op?: Op;
  property: Property;
  value: Value;
  [k: string]: unknown;
}
