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
export type Classification = string;
export type HandlingCode = string;
export type OwningUnit = string;
export type Originator = string;
export type Handlings = CountedHandling[];

export interface TrendResult {
  interval: TrendInterval;
  measure: TrendMeasure;
  points: Points;
  series?: Series1;
  total: Total;
  events: Events;
  unvalued?: Unvalued;
  classifications?: Classifications;
  handlings?: Handlings;
  [k: string]: unknown;
}
export interface TrendPoint {
  period_start: PeriodStart;
  series?: Series;
  value: Value;
  [k: string]: unknown;
}
/**
 * One distinct handling among the events a trend counted: what a reader of a frozen snapshot
 * must be able to view (ADR-113 Amendment 1) — the restricted code and its units, not only the
 * classification.
 */
export interface CountedHandling {
  classification: Classification;
  handling_code: HandlingCode;
  owning_unit: OwningUnit;
  originator: Originator;
  [k: string]: unknown;
}
