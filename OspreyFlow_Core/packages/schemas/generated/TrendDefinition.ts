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
export type Id = string;
export type InvestigationId = string;
export type CreatedBy = string;
export type CreatedAt = string;
export type UpdatedAt = string;

export interface TrendDefinition {
  title: Title;
  event_types: EventTypes;
  measure?: TrendMeasure;
  measure_field?: MeasureField;
  interval?: TrendInterval;
  weeks?: Weeks;
  group_by?: GroupBy;
  filters?: Filters;
  id: Id;
  investigation_id: InvestigationId;
  created_by: CreatedBy;
  created_at: CreatedAt;
  updated_at: UpdatedAt;
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
