// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Title = string;
/**
 * @minItems 1
 * @maxItems 12
 */
export type EventTypes =
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string];
export type TrendMeasure = "count" | "sum";
export type MeasureField = string | null;
export type TrendInterval = "week" | "month";
export type Weeks = number;
export type GroupBy = string | null;
/**
 * @maxItems 5
 */
export type Filters =
  | []
  | [TrendFilter]
  | [TrendFilter, TrendFilter]
  | [TrendFilter, TrendFilter, TrendFilter]
  | [TrendFilter, TrendFilter, TrendFilter, TrendFilter]
  | [TrendFilter, TrendFilter, TrendFilter, TrendFilter, TrendFilter];
export type Field = string;
export type Value = string;
export type TrendInterval1 = "week" | "month";
export type TrendMeasure1 = "count" | "sum";
export type PeriodStart = string;
export type Series = string | null;
export type Value1 = number;
export type Points = TrendPoint[];
export type Series1 = string[];
export type Total = number;
export type Events = number;
export type Unvalued = number;
export type Classifications = string[];
export type AsOf = string;
export type WindowStart = string;
export type Marking = string | null;

/**
 * A trend computed for the reader at `as_of` — never stored; a pack keeps a snapshot.
 */
export interface TrendFigures {
  definition: TrendDefinitionInput;
  result: TrendResult;
  as_of: AsOf;
  window_start: WindowStart;
  marking?: Marking;
  [k: string]: unknown;
}
export interface TrendDefinitionInput {
  title: Title;
  event_types: EventTypes;
  measure?: TrendMeasure;
  measure_field?: MeasureField;
  interval?: TrendInterval;
  weeks?: Weeks;
  group_by?: GroupBy;
  filters?: Filters;
  [k: string]: unknown;
}
/**
 * Only events whose property equals this value.
 */
export interface TrendFilter {
  field: Field;
  value: Value;
  [k: string]: unknown;
}
export interface TrendResult {
  interval: TrendInterval1;
  measure: TrendMeasure1;
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
  value: Value1;
  [k: string]: unknown;
}
