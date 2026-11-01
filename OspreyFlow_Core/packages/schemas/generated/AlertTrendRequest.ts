// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationScope = string;
export type ValidFrom = string;
export type ValidTo = string | null;
export type TrendInterval = "week" | "month";
export type GroupBy = ("rule" | "typology" | "severity" | "outcome") | null;
export type MaxPeriods = number;
export type MaxSeries = number;

/**
 * Alerts raised per week or month, optionally split by one field and narrowed by up to five
 * equalities — a closed definition, counted as the reader (ADR-134 decision 3).
 */
export interface AlertTrendRequest {
  investigation_scope: InvestigationScope;
  window: Interval;
  interval?: TrendInterval;
  group_by?: GroupBy;
  filters?: Filters;
  max_periods?: MaxPeriods;
  max_series?: MaxSeries;
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
export interface Filters {
  [k: string]: string[];
}
