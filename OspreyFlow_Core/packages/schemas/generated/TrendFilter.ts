// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Field = string;
export type Value = string;

/**
 * Only events whose property equals this value.
 */
export interface TrendFilter {
  field: Field;
  value: Value;
  [k: string]: unknown;
}
