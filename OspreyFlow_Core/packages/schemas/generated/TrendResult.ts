// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type TrendInterval = "week" | "month";
export type TrendMeasure = "count" | "sum";
export type PeriodStart = string;
export type Series = string | null;
export type Value = number;
export type Points = TrendPoint[];
export type Series1 = string[];
export type Total = number;
export type Events = number;
export type Unvalued = number;
export type Classifications = string[];

export interface TrendResult {
  interval: TrendInterval;
  measure: TrendMeasure;
  points: Points;
  series?: Series1;
  total: Total;
  events: Events;
  unvalued?: Unvalued;
  classifications?: Classifications;
  [k: string]: unknown;
}
export interface TrendPoint {
  period_start: PeriodStart;
  series?: Series;
  value: Value;
  [k: string]: unknown;
}
