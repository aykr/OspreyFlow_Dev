// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "structuring";
export type Threshold = number;
export type WindowDays = number;
export type MinimumCount = number;

export interface StructuringParams {
  typology?: Typology;
  threshold: Threshold;
  window_days: WindowDays;
  minimum_count: MinimumCount;
  [k: string]: unknown;
}
