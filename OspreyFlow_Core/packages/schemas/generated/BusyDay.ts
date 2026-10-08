// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Start = string;
export type End = string;
export type Count = number;

export interface BusyDay {
  start: Start;
  end: End;
  count: Count;
  [k: string]: unknown;
}
