// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "circular_flow";
export type MaxHops = number;
export type WindowDays = number;

export interface CircularFlowParams {
  typology?: Typology;
  max_hops: MaxHops;
  window_days: WindowDays;
  [k: string]: unknown;
}
