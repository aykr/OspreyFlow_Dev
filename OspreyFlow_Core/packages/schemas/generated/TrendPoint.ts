// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PeriodStart = string;
export type Series = string | null;
export type Value = number;

export interface TrendPoint {
  period_start: PeriodStart;
  series?: Series;
  value: Value;
  [k: string]: unknown;
}
